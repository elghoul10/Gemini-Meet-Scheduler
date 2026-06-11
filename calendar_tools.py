# calendar_tools.py
import datetime
import os.path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import dateparser
from google.auth.transport.requests import Request  # Ensure this is here
from typing import List, Optional

# calendar_tools.py (Updated)
import datetime
import os.path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import dateparser
from google.auth.transport.requests import Request

# calendar_tools.py (Updated - FIX for SyntaxError)
import datetime
import os.path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import dateparser
from google.auth.transport.requests import Request

# calendar_tools.py (Modified to use project root for creds/token)
import datetime
import os.path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import dateparser
from google.auth.transport.requests import Request

SCOPES = ['https://www.googleapis.com/auth/calendar']

# Determine the project root dynamically based on this file's location
# Assumes calendar_tools.py is in a subdirectory of the project root
# e.g., project_root/meeting_agent/calendar_tools.py
# Adjust `os.pardir` count if your structure is deeper.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
CREDENTIALS_FILE_NAME = 'credentials.json'
TOKEN_FILE_NAME = 'token.json'

CREDENTIALS_PATH = os.path.join(PROJECT_ROOT, CREDENTIALS_FILE_NAME)
TOKEN_PATH = os.path.join(PROJECT_ROOT, TOKEN_FILE_NAME)

print(f"DEBUG: Credentials will be expected at: {CREDENTIALS_PATH}")
print(f"DEBUG: Token will be saved/loaded from: {TOKEN_PATH}")


# MODIFICATION: Removed credentials_path parameter
def get_calendar_service():
    """Shows basic usage of the Google Calendar API.
    Handles authentication and returns the service object.
    Expects credentials.json to be in the PROJECT_ROOT.
    """
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_PATH):
                raise FileNotFoundError(
                    f"credentials.json not found at {CREDENTIALS_PATH}. "
                    "Please upload it via Streamlit or place it in the project root."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_PATH, SCOPES)  # Use fixed path
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, 'w') as token:  # Save token to fixed path
            token.write(creds.to_json())
    return build('calendar', 'v3', credentials=creds)


# All other functions (schedule_meeting_natural, list_events_natural_time,
# find_events_by_summary, update_event_natural) no longer need to accept
# a 'credentials_path' argument. They will call get_calendar_service() without it.

# Example for schedule_meeting_natural - apply this pattern to all functions
def schedule_meeting_natural(
        start_time_natural: str,
        duration_minutes: int,
        attendees_emails: list,
        summary="Meeting"  # Removed credentials_path as parameter
):
    service = get_calendar_service()  # No argument needed now
    # ... rest of the function remains the same ...
    parsed_time = dateparser.parse(start_time_natural, settings={'TIMEZONE': 'UTC', 'RETURN_AS_TIMEZONE_AWARE': True})
    if not parsed_time:
        return f"Could not understand the date/time: '{start_time_natural}'"

    start = parsed_time
    end = start + datetime.timedelta(minutes=duration_minutes)

    event = {
        'summary': summary,
        'start': {
            'dateTime': start.isoformat(),
            'timeZone': 'UTC'
        },
        'end': {
            'dateTime': end.isoformat(),
            'timeZone': 'UTC'
        },
        'attendees': [{'email': email} for email in attendees_emails],
        'reminders': {
            'useDefault': False,
            'overrides': [
                {'method': 'email', 'minutes': 24 * 60},
                {'method': 'popup', 'minutes': 10},
            ],
        },
    }

    try:
        event = service.events().insert(calendarId='primary', body=event, sendUpdates='all').execute()
        return f"Meeting scheduled: {event.get('htmlLink')}"
    except Exception as e:
        return f"Error scheduling meeting: {e}"


# --- Update list_events_natural_time, find_events_by_summary, update_event_natural ---
# REMOVE the 'credentials_path: str = None' parameter from all of them
# And remove the 'if credentials_path is None:' check.
# They should simply call service = get_calendar_service()

def list_events_natural_time(time_frame_natural: str) -> str:  # Parameter removed
    service = get_calendar_service()  # No argument needed now
    # ... rest of list_events_natural_time function ...
    now = datetime.datetime.now(datetime.timezone.utc)
    # Initialize start and end with broad defaults for safety
    timeMin = datetime.datetime.combine(now.date(), datetime.time.min, tzinfo=datetime.timezone.utc)  # Start of today
    timeMax = datetime.datetime.combine(now.date() + datetime.timedelta(days=30), datetime.time.max,
                                        tzinfo=datetime.timezone.utc)  # Next 30 days

    # More specific handling for common phrases:
    if "today" in time_frame_natural.lower():
        timeMin = datetime.datetime.combine(now.date(), datetime.time.min, tzinfo=datetime.timezone.utc)
        timeMax = datetime.datetime.combine(now.date(), datetime.time.max, tzinfo=datetime.timezone.utc)
    elif "tomorrow" in time_frame_natural.lower():
        tomorrow = now.date() + datetime.timedelta(days=1)
        timeMin = datetime.datetime.combine(tomorrow, datetime.time.min, tzinfo=datetime.timezone.utc)
        timeMax = datetime.datetime.combine(tomorrow, datetime.time.max, tzinfo=datetime.timezone.utc)
    elif "this week" in time_frame_natural.lower():
        days_ahead_to_monday = (0 - now.weekday()) % 7  # 0 is Monday
        start_of_week = now + datetime.timedelta(days=days_ahead_to_monday)
        timeMin = datetime.datetime.combine(start_of_week.date(), datetime.time.min, tzinfo=datetime.timezone.utc)
        timeMax = datetime.datetime.combine(start_of_week.date() + datetime.timedelta(days=7), datetime.time.max,
                                            tzinfo=datetime.timezone.utc)
    elif "next week" in time_frame_natural.lower():
        days_ahead_to_next_monday = (0 - now.weekday()) % 7 + 7  # Next Monday
        start_of_next_week = now + datetime.timedelta(days=days_ahead_to_next_monday)
        timeMin = datetime.datetime.combine(start_of_next_week.date(), datetime.time.min, tzinfo=datetime.timezone.utc)
        timeMax = datetime.datetime.combine(start_of_next_week.date() + datetime.timedelta(days=7), datetime.time.max,
                                            tzinfo=datetime.timezone.utc)
    else:  # Fallback to generic dateparser for other phrases
        parsed_start_time = dateparser.parse(time_frame_natural,
                                             settings={'TIMEZONE': 'UTC', 'RETURN_AS_TIMEZONE_AWARE': True,
                                                       'PREFER_DATES_FROM': 'future'})
        if parsed_start_time:
            timeMin = parsed_start_time
            # If a specific time is parsed, narrow window to a few hours
            if parsed_start_time.hour != 0 or parsed_start_time.minute != 0:
                timeMax = timeMin + datetime.timedelta(hours=3)  # Search 3 hours around specific time
            else:  # If only date (midnight), search the whole day
                timeMax = datetime.datetime.combine(timeMin.date(), datetime.time.max, tzinfo=datetime.timezone.utc)
        else:
            return f"Could not understand the time frame: '{time_frame_natural}'"  # If still can't parse

    events_result = service.events().list(calendarId='primary', timeMin=timeMin.isoformat(),
                                          timeMax=timeMax.isoformat(), singleEvents=True,
                                          orderBy='startTime').execute()
    events = events_result.get('items', [])

    if not events:
        return f"No upcoming events found for '{time_frame_natural}' within the search window."

    output = f"Events for '{time_frame_natural}':\n"
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        end = event['end'].get('dateTime', event['end'].get('date'))

        try:
            # Use current system's timezone for display
            local_tz = datetime.datetime.now().astimezone().tzinfo
            start_dt = dateparser.parse(start,
                                        settings={'TIMEZONE': 'UTC', 'RETURN_AS_TIMEZONE_AWARE': True}).astimezone(
                local_tz)
            end_dt = dateparser.parse(end, settings={'TIMEZONE': 'UTC', 'RETURN_AS_TIMEZONE_AWARE': True}).astimezone(
                local_tz)

            time_str = start_dt.strftime('%Y-%m-%d %I:%M %p')
            if start_dt.hour == 0 and start_dt.minute == 0 and 'date' in event['start'] and 'dateTime' not in event[
                'start']:  # All-day event
                time_str = start_dt.strftime('%Y-%m-%d (All Day)')
            elif start_dt.date() == end_dt.date():  # Same-day timed event
                time_str += f" - {end_dt.strftime('%I:%M %p')}"
            else:  # Multi-day timed event
                time_str = f"{start_dt.strftime('%Y-%m-%d %I:%M %p')} to {end_dt.strftime('%Y-%m-%d %I:%M %p')}"
        except Exception:
            time_str = start  # Fallback if parsing fails

        output += f"- {event['summary']} ({time_str})\n"
    return output


def find_events_by_summary(summary_keyword: str, time_frame_natural: Optional[str] = None) -> List[
    dict]:  # Parameter removed
    service = get_calendar_service()  # No argument needed now
    # ... rest of find_events_by_summary function ...
    now = datetime.datetime.now(datetime.timezone.utc)

    # Default search from the start of today, for the next 7 days, for robustness
    timeMin = datetime.datetime.combine(now.date(), datetime.time.min, tzinfo=datetime.timezone.utc)
    timeMax = timeMin + datetime.timedelta(days=7)  # Default search window of one week

    if time_frame_natural:
        if "today" in time_frame_natural.lower():
            timeMin = datetime.datetime.combine(now.date(), datetime.time.min, tzinfo=datetime.timezone.utc)
            timeMax = datetime.datetime.combine(now.date(), datetime.time.max, tzinfo=datetime.timezone.utc)
        elif "tomorrow" in time_frame_natural.lower():
            tomorrow = now.date() + datetime.timedelta(days=1)
            timeMin = datetime.datetime.combine(tomorrow, datetime.time.min, tzinfo=datetime.timezone.utc)
            timeMax = datetime.datetime.combine(tomorrow, datetime.time.max, tzinfo=datetime.timezone.utc)
        elif "this week" in time_frame_natural.lower():
            days_ahead_to_monday = (0 - now.weekday()) % 7  # 0 is Monday
            start_of_week = now + datetime.timedelta(days=days_ahead_to_monday)
            timeMin = datetime.datetime.combine(start_of_week.date(), datetime.time.min, tzinfo=datetime.timezone.utc)
            timeMax = datetime.datetime.combine(start_of_week.date() + datetime.timedelta(days=7), datetime.time.max,
                                                tzinfo=datetime.timezone.utc)
        elif "next week" in time_frame_natural.lower():
            days_ahead_to_next_monday = (0 - now.weekday()) % 7 + 7  # Next Monday
            start_of_next_week = now + datetime.timedelta(days=days_ahead_to_next_monday)
            timeMin = datetime.datetime.combine(start_of_next_week.date(), datetime.time.min,
                                                tzinfo=datetime.timezone.utc)
            timeMax = datetime.datetime.combine(start_of_next_week.date() + datetime.timedelta(days=7),
                                                datetime.time.max, tzinfo=datetime.timezone.utc)
        else:  # Generic parsing if no specific keyword matches
            parsed_time = dateparser.parse(time_frame_natural,
                                           settings={'TIMEZONE': 'UTC', 'RETURN_AS_TIMEZONE_AWARE': True,
                                                     'PREFER_DATES_FROM': 'future'})
            if parsed_time:
                timeMin = parsed_time
                if parsed_time.hour == 0 and parsed_time.minute == 0:  # If only date
                    timeMax = datetime.datetime.combine(timeMin.date(), datetime.time.max, tzinfo=datetime.timezone.utc)
                else:  # If specific time, search a small window around it for safety
                    timeMax = timeMin + datetime.timedelta(hours=3)
            # If dateparser fails, timeMin/timeMax remain at default (1 week from now)

    events_result = service.events().list(calendarId='primary',
                                          timeMin=timeMin.isoformat(),
                                          timeMax=timeMax.isoformat(),
                                          q=summary_keyword,  # Search by summary
                                          singleEvents=True,
                                          orderBy='startTime').execute()
    events = events_result.get('items', [])
    return events


def update_event_natural(
        event_id: str,
        new_start_time_natural: Optional[str] = None,
        new_duration_minutes: Optional[int] = None,
        new_summary: Optional[str] = None,
        new_attendees_emails: Optional[List[str]] = None
) -> str:  # Removed credentials_path as parameter
    service = get_calendar_service()  # No argument needed now
    # ... rest of update_event_natural function ...
    try:
        event = service.events().get(calendarId='primary', eventId=event_id).execute()
    except Exception as e:
        return f"Error: Could not find event with ID '{event_id}'. {e}"

    # Get original start and end datetime objects in UTC
    original_start_dt_utc = dateparser.parse(event['start'].get('dateTime', event['start'].get('date')),
                                             settings={'TIMEZONE': 'UTC', 'RETURN_AS_TIMEZONE_AWARE': True})
    original_end_dt_utc = dateparser.parse(event['end'].get('dateTime', event['end'].get('date')),
                                           settings={'TIMEZONE': 'UTC', 'RETURN_AS_TIMEZONE_AWARE': True})

    # Calculate original duration if it's a timed event
    original_duration_minutes = None
    if original_start_dt_utc and original_end_dt_utc and 'dateTime' in event['start']:
        original_duration_minutes = int((original_end_dt_utc - original_start_dt_utc).total_seconds() / 60)
    elif 'date' in event['start'] and 'date' in event['end']:  # All-day event
        # All-day duration is handled differently, often just start/end dates
        pass  # Don't apply 'duration_minutes' for all-day

    # Update start time
    if new_start_time_natural:
        parsed_new_time = dateparser.parse(new_start_time_natural,
                                           settings={'TIMEZONE': 'UTC', 'RETURN_AS_TIMEZONE_AWARE': True})
        if not parsed_new_time:
            return f"Error: Could not understand the new start time: '{new_start_time_natural}'"

        # Determine new duration: new_duration_minutes, then original, then default
        duration_to_use = new_duration_minutes if new_duration_minutes is not None else original_duration_minutes
        if duration_to_use is None:
            duration_to_use = 30  # Default to 30 min if no duration can be determined

        event['start']['dateTime'] = parsed_new_time.isoformat()
        event['end']['dateTime'] = (parsed_new_time + datetime.timedelta(minutes=duration_to_use)).isoformat()
        event['start']['timeZone'] = event['start'].get('timeZone', 'UTC')
        event['end']['timeZone'] = event['end'].get('timeZone', 'UTC')
        # If it was an all-day event but now a specific time is given, update to dateTime
        if 'date' in event['start']: del event['start']['date']
        if 'date' in event['end']: del event['end']['date']  # Make sure to clear date fields

    # Update duration if only duration is provided (and it's a timed event)
    if new_duration_minutes is not None and not new_start_time_natural:
        if 'dateTime' in event['start']:  # Only if it's currently a timed event
            current_start_dt_utc = dateparser.parse(event['start']['dateTime'],
                                                    settings={'TIMEZONE': 'UTC', 'RETURN_AS_TIMEZONE_AWARE': True})
            event['end']['dateTime'] = (
                        current_start_dt_utc + datetime.timedelta(minutes=new_duration_minutes)).isoformat()
            event['end']['timeZone'] = event['end'].get('timeZone', 'UTC')
        else:  # If it's an all-day event, new duration implies it might become a timed event, which requires new_start_time
            return "Error: Cannot set duration for an all-day event without also specifying a new start time."

    # Update summary
    if new_summary:
        event['summary'] = new_summary

    # Update attendees
    if new_attendees_emails is not None:  # Can be an empty list to clear attendees
        event['attendees'] = [{'email': email} for email in new_attendees_emails]
    # IMPORTANT: If new_attendees_emails is None, we don't modify the existing attendees.

    updated_event = service.events().update(calendarId='primary', eventId=event['id'], body=event,
                                            sendUpdates='all').execute()
    return f"Meeting updated: {updated_event.get('htmlLink')}"