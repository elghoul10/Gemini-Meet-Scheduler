"""
agent.py — Refactored to use standard HTTP requests (no google-generativeai SDK).
Compatible with Python 3.8+.
"""
import os
import json
import re
import datetime
import dateparser
import pandas as pd
import requests
from typing import List, Optional

from calendar_tools import schedule_meeting_natural, list_events_natural_time, find_events_by_summary, \
    update_event_natural
from csv_tools import get_email_from_csv, add_collaborator, _ensure_csv_exists_with_headers


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict:
    """Pull the first JSON object out of a model response string."""
    # Strip markdown fences if present
    text = re.sub(r"```(?:json)?", "", text).strip().strip("`").strip()
    # Find first {...}
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {}


def _call_model(api_key: str, prompt: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1}
    }
    
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code != 200:
        raise Exception(f"Gemini API returned {response.status_code}: {response.text}")
        
    data = response.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError):
        return ""


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------

class MeetingSchedulerAgent:
    def __init__(self, gemini_api_key: str):
        self.gemini_api_key = gemini_api_key

        self.current_task = {
            "intent": None,
            "meeting": {"time": None, "duration": None, "attendees": [], "summary": None, "attendee_emails": []},
            "collaborator": {"name": None, "email": None},
            "list_events": {"time_frame": None},
            "modify_meeting": {
                "event_id": None, "summary_keyword": None, "time_frame_to_search": None,
                "new_time": None, "new_duration": None, "new_attendees": [], "new_summary": None,
                "new_attendee_emails": []
            },
            "event_search_results": []
        }
        self.conversation_history = ""

        _ensure_csv_exists_with_headers()

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def reset_current_task(self):
        self.current_task = {
            "intent": None,
            "meeting": {"time": None, "duration": None, "attendees": [], "summary": None, "attendee_emails": []},
            "collaborator": {"name": None, "email": None},
            "list_events": {"time_frame": None},
            "modify_meeting": {
                "event_id": None, "summary_keyword": None, "time_frame_to_search": None,
                "new_time": None, "new_duration": None, "new_attendees": [], "new_summary": None,
                "new_attendee_emails": []
            },
            "event_search_results": []
        }
        self.conversation_history = ""

    def update_meeting_state(self, d: dict):
        if d.get("time"):      self.current_task["meeting"]["time"] = d["time"]
        if d.get("duration"):  self.current_task["meeting"]["duration"] = d["duration"]
        if d.get("summary"):   self.current_task["meeting"]["summary"] = d["summary"]
        for name in (d.get("attendees") or []):
            if name and name not in self.current_task["meeting"]["attendees"]:
                self.current_task["meeting"]["attendees"].append(name)

    def update_collaborator_state(self, d: dict):
        if d.get("name"):  self.current_task["collaborator"]["name"] = d["name"]
        if d.get("email"): self.current_task["collaborator"]["email"] = d["email"]

    def update_list_events_state(self, d: dict):
        if d.get("time_frame"): self.current_task["list_events"]["time_frame"] = d["time_frame"]

    def update_modify_meeting_state(self, d: dict):
        if d.get("event_id"):           self.current_task["modify_meeting"]["event_id"] = d["event_id"]
        if d.get("summary_keyword"):    self.current_task["modify_meeting"]["summary_keyword"] = d["summary_keyword"]
        if d.get("time_frame_to_search"): self.current_task["modify_meeting"]["time_frame_to_search"] = d["time_frame_to_search"]
        if d.get("new_time"):           self.current_task["modify_meeting"]["new_time"] = d["new_time"]
        if d.get("new_duration"):       self.current_task["modify_meeting"]["new_duration"] = d["new_duration"]
        if d.get("new_summary"):        self.current_task["modify_meeting"]["new_summary"] = d["new_summary"]
        for name in (d.get("new_attendees") or []):
            if name and name not in self.current_task["modify_meeting"]["new_attendees"]:
                self.current_task["modify_meeting"]["new_attendees"].append(name)

    def get_missing_meeting_slots(self):
        m = self.current_task["meeting"]
        missing = []
        if not m["time"]:      missing.append("time")
        if not m["duration"]:  missing.append("duration")
        if not m["attendees"]: missing.append("attendees")
        return missing

    def get_missing_collaborator_slots(self):
        c = self.current_task["collaborator"]
        missing = []
        if not c["name"]:  missing.append("name")
        if not c["email"]: missing.append("email")
        return missing

    def get_missing_list_events_slots(self):
        return [] if self.current_task["list_events"]["time_frame"] else ["time_frame"]

    def get_missing_modify_meeting_slots(self):
        m = self.current_task["modify_meeting"]
        if not m["event_id"] and not m["summary_keyword"]:
            return ["event_identifier"]
        if not (m["new_time"] or m["new_duration"] or m["new_attendees"] or m["new_summary"]):
            return ["modification_details"]
        return []

    # ------------------------------------------------------------------
    # LLM calls (direct REST endpoints)
    # ------------------------------------------------------------------

    def _detect_intent(self, user_input: str, current_datetime: str) -> str:
        prompt = f"""
Current Date and Time: {current_datetime}
Given the user's message and conversation history, identify the primary intent.
Possible intents: SCHEDULE_MEETING, ADD_COLLABORATOR, LIST_EVENTS, MODIFY_MEETING, INQUIRY.
Return ONLY one of these words, nothing else.

Conversation History:
{self.conversation_history}
User message: {user_input}
Intent:"""
        raw = _call_model(self.gemini_api_key, prompt)
        for intent in ["SCHEDULE_MEETING", "ADD_COLLABORATOR", "LIST_EVENTS", "MODIFY_MEETING", "INQUIRY"]:
            if intent in raw.upper():
                return intent
        return "INQUIRY"

    def _extract_meeting_info(self, user_input: str, current_datetime: str) -> dict:
        prompt = f"""
Current Date and Time: {current_datetime}
Extract meeting details from the user's message.
Return a JSON object with these keys: time (string or null), duration (integer minutes or null), attendees (list of strings), summary (string or null).
Return ONLY the JSON object, nothing else.

User message: {user_input}"""
        raw = _call_model(self.gemini_api_key, prompt)
        return _extract_json(raw)

    def _extract_collaborator_info(self, user_input: str, current_datetime: str) -> dict:
        prompt = f"""
Current Date and Time: {current_datetime}
Extract a collaborator's name and email from the user's message.
Return a JSON object with keys: name (string or null), email (string or null).
Return ONLY the JSON object, nothing else.

User message: {user_input}"""
        raw = _call_model(self.gemini_api_key, prompt)
        return _extract_json(raw)

    def _extract_list_events_info(self, user_input: str, current_datetime: str) -> dict:
        prompt = f"""
Current Date and Time: {current_datetime}
Extract a time frame for listing calendar events from the user's message.
Return a JSON object with key: time_frame (string or null).
Return ONLY the JSON object, nothing else.

User message: {user_input}"""
        raw = _call_model(self.gemini_api_key, prompt)
        return _extract_json(raw)

    def _extract_modify_meeting_info(self, user_input: str, current_datetime: str) -> dict:
        prompt = f"""
Current Date and Time: {current_datetime}
Extract details for modifying an existing meeting from the user's message.
Return a JSON object with keys: event_id (string or null), summary_keyword (string or null),
time_frame_to_search (string or null), new_time (string or null), new_duration (integer or null),
new_attendees (list of strings), new_summary (string or null).
Return ONLY the JSON object, nothing else.

User message: {user_input}"""
        raw = _call_model(self.gemini_api_key, prompt)
        return _extract_json(raw)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def process_user_input(self, user_input: str) -> str:
        current_datetime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        response = ""

        # --- Intent detection ---
        new_intent = self._detect_intent(user_input, current_datetime)

        if self.current_task["intent"] is None or new_intent != "INQUIRY":
            if new_intent != self.current_task["intent"] and self.current_task["intent"] is not None:
                response += f"Okay, switching to {new_intent.replace('_', ' ').lower()}.\n"
            self.current_task["intent"] = new_intent

        # --- ADD_COLLABORATOR ---
        if self.current_task["intent"] == "ADD_COLLABORATOR":
            try:
                extracted = self._extract_collaborator_info(user_input, current_datetime)
                self.update_collaborator_state(extracted)
            except Exception as e:
                return f"Agent Error: Could not extract collaborator info. ({e})"

            missing = self.get_missing_collaborator_slots()
            if missing:
                response = "What's their name?" if "name" in missing else "And their email?"
            else:
                result = add_collaborator(self.current_task["collaborator"]["name"],
                                         self.current_task["collaborator"]["email"])
                response = f"Okay, adding collaborator...\n{result}\nAnything else?"
                self.reset_current_task()

        # --- LIST_EVENTS ---
        elif self.current_task["intent"] == "LIST_EVENTS":
            try:
                extracted = self._extract_list_events_info(user_input, current_datetime)
                self.update_list_events_state(extracted)
            except Exception as e:
                return f"Agent Error: Could not extract time frame. ({e})"

            missing = self.get_missing_list_events_slots()
            if missing:
                response = "For what time frame should I list events? (e.g., 'tomorrow', 'next week')"
            else:
                tf = self.current_task["list_events"]["time_frame"]
                result = list_events_natural_time(tf)
                response = f"Okay, listing events for '{tf}'...\n{result}\nAnything else?"
                self.reset_current_task()

        # --- SCHEDULE_MEETING ---
        elif self.current_task["intent"] == "SCHEDULE_MEETING":
            try:
                extracted = self._extract_meeting_info(user_input, current_datetime)
                self.update_meeting_state(extracted)
            except Exception as e:
                return f"Agent Error: Could not extract meeting info. ({e})"

            # Try to resolve attendee emails eagerly
            if self.current_task["meeting"]["attendees"] and not self.current_task["meeting"]["attendee_emails"]:
                missing_emails = []
                resolved = []
                for name in self.current_task["meeting"]["attendees"]:
                    email = get_email_from_csv(name)
                    if email:
                        resolved.append(email)
                    else:
                        missing_emails.append(name)
                if missing_emails:
                    return f"I don't have an email for {' and '.join(missing_emails)}. What is their email?"
                self.current_task["meeting"]["attendee_emails"] = resolved

            # Check for ambiguous time (date but no time)
            if self.current_task["meeting"]["time"]:
                parsed_dt = dateparser.parse(
                    self.current_task["meeting"]["time"],
                    settings={"DATE_ORDER": "DMY", "TIMEZONE": "UTC", "RETURN_AS_TIMEZONE_AWARE": True}
                )
                if parsed_dt and parsed_dt.hour == 0 and parsed_dt.minute == 0 and \
                        "at" not in self.current_task["meeting"]["time"].lower():
                    return "What specific time should the meeting be? (e.g., 'at 9am')"

            missing = self.get_missing_meeting_slots()
            if missing:
                if "time" in missing:
                    response = "When should the meeting be? (e.g., 'tomorrow at 3pm')"
                elif "duration" in missing:
                    response = "For how long? (in minutes)"
                elif "attendees" in missing:
                    response = "Who should attend the meeting?"
            else:
                # Final email resolution
                final_emails = []
                missing_at_end = []
                for name in self.current_task["meeting"]["attendees"]:
                    email = get_email_from_csv(name)
                    if email:
                        final_emails.append(email)
                    else:
                        missing_at_end.append(name)
                if missing_at_end:
                    return f"I still need emails for {' and '.join(missing_at_end)}. Please add them as collaborators first."

                result = schedule_meeting_natural(
                    start_time_natural=self.current_task["meeting"]["time"],
                    duration_minutes=self.current_task["meeting"]["duration"],
                    attendees_emails=final_emails,
                    summary=self.current_task["meeting"]["summary"] or
                            f"Meeting with {', '.join(self.current_task['meeting']['attendees'])}"
                )
                response = f"Okay, scheduling meeting...\n{result}\nDone! Anything else?"
                self.reset_current_task()

        # --- MODIFY_MEETING ---
        elif self.current_task["intent"] == "MODIFY_MEETING":
            try:
                extracted = self._extract_modify_meeting_info(user_input, current_datetime)
                self.update_modify_meeting_state(extracted)
            except Exception as e:
                return f"Agent Error: Could not extract modification details. ({e})"

            modify_state = self.current_task["modify_meeting"]

            if not modify_state["event_id"]:
                if not modify_state["summary_keyword"] and not modify_state["time_frame_to_search"]:
                    return "Which meeting do you want to modify? Please give me its name or approximate time."

                found = find_events_by_summary(modify_state["summary_keyword"], modify_state["time_frame_to_search"])
                if not found:
                    self.reset_current_task()
                    return f"I couldn't find any meetings matching '{modify_state.get('summary_keyword', '')}'. Try listing events first."
                elif len(found) == 1:
                    event = found[0]
                    self.current_task["modify_meeting"]["event_id"] = event["id"]
                    start_time = event["start"].get("dateTime", event["start"].get("date"))
                    return f"Found: '{event['summary']}' on {start_time}. What do you want to change?"
                else:
                    self.current_task["event_search_results"] = found
                    lines = ["I found multiple events. Which one do you want to modify?"]
                    for i, ev in enumerate(found):
                        st = ev["start"].get("dateTime", ev["start"].get("date"))
                        lines.append(f"{i+1}. {ev['summary']} ({st})")
                    return "\n".join(lines) + "\nPlease reply with the number."

            # User selected a number from list
            if self.current_task["event_search_results"] and user_input.strip().isdigit():
                sel = int(user_input.strip())
                results = self.current_task["event_search_results"]
                if 1 <= sel <= len(results):
                    chosen = results[sel - 1]
                    self.current_task["modify_meeting"]["event_id"] = chosen["id"]
                    self.current_task["event_search_results"] = []
                    return f"Okay, selected '{chosen['summary']}'. What do you want to change?"
                else:
                    return "Invalid selection. Please choose a valid number."

            missing_mod = self.get_missing_modify_meeting_slots()
            if missing_mod:
                if "modification_details" in missing_mod:
                    return "What do you want to change? (e.g., 'move it to 11am', 'change duration to 60 minutes')"
                return response

            # Resolve new attendee emails
            new_emails = []
            missing_new = []
            if modify_state["new_attendees"]:
                for name in modify_state["new_attendees"]:
                    email = get_email_from_csv(name)
                    if email:
                        new_emails.append(email)
                    else:
                        missing_new.append(name)
                if missing_new:
                    return f"I need the email for {' and '.join(missing_new)} to add them."
            self.current_task["modify_meeting"]["new_attendee_emails"] = new_emails

            result = update_event_natural(
                event_id=modify_state["event_id"],
                new_start_time_natural=modify_state["new_time"],
                new_duration_minutes=modify_state["new_duration"],
                new_summary=modify_state["new_summary"],
                new_attendees_emails=new_emails if modify_state["new_attendees"] else None
            )
            response = f"Okay, updating...\n{result}\nAnything else?"
            self.reset_current_task()

        else:
            response = "I can help schedule, list, or modify meetings, and add collaborators. What would you like to do?"
            self.reset_current_task()

        # Update history (keep last 4 lines)
        self.conversation_history = "\n".join(
            (self.conversation_history + f"\nYou: {user_input}\nAgent: {response.replace(chr(10), ' ')}").split("\n")[-4:]
        )

        return response