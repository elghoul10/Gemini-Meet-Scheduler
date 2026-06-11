# streamlit_app.py (Modified)
import streamlit as st
import os
import json
# Removed tempfile as it's no longer needed for creds
from agent import MeetingSchedulerAgent
from calendar_tools import CREDENTIALS_PATH  # Import the fixed path from calendar_tools

st.set_page_config(page_title="Meeting Scheduler AI", layout="centered")

st.title("Meeting Scheduler AI Assistant")

# --- Configuration Section ---
st.sidebar.header("Configuration")
gemini_api_key = st.sidebar.text_input("Gemini API Key", type="password")
uploaded_credentials = st.sidebar.file_uploader("Upload Google Calendar credentials.json", type=["json"])

# --- Session State Initialization ---
if "agent" not in st.session_state:
    st.session_state.agent = None
if "messages" not in st.session_state:
    st.session_state.messages = []


# --- Agent Initialization Logic ---
def initialize_agent_and_chat():
    if not gemini_api_key:
        st.error("Please enter your Gemini API Key.")
        return
    if not uploaded_credentials:
        st.error("Please upload your Google Calendar credentials.json.")
        return

    # Save uploaded credentials directly to the project root
    try:
        with open(CREDENTIALS_PATH, "wb") as f:
            f.write(uploaded_credentials.getvalue())
        st.info(f"Credentials saved to: {CREDENTIALS_PATH}")
        # Ensure token.json is removed if it exists, to force re-authentication with new creds
        token_path = CREDENTIALS_PATH.replace('credentials.json', 'token.json')
        if os.path.exists(token_path):
            os.remove(token_path)
            st.warning(f"Removed existing token.json at {token_path} to force re-authentication.")

    except Exception as e:
        st.error(f"Error saving credentials file to project root: {e}")
        return

    try:
        # Initialize the agent (NO credentials_file_path argument now)
        st.session_state.agent = MeetingSchedulerAgent(
            gemini_api_key=gemini_api_key
        )
        st.session_state.messages = [{"role": "assistant", "content": "Hi! How can I assist you today?"}]
        st.sidebar.success(
            "Agent and Calendar API initialized! (You may need to re-authenticate Google Calendar in your browser.)")
    except FileNotFoundError as e:  # Catch specific error from get_calendar_service if creds not found
        st.error(f"Error: {e}. Please ensure credentials.json is correctly uploaded/placed.")
        st.session_state.agent = None
    except Exception as e:
        st.error(f"Error initializing agent or Calendar API: {e}")
        st.session_state.agent = None


if st.sidebar.button("Start Chat / Re-initialize Agent"):
    initialize_agent_and_chat()

# --- Chat Interface ---
if st.session_state.agent:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("What would you like to do?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.spinner("Thinking..."):
            agent_response = st.session_state.agent.process_user_input(prompt)

        with st.chat_message("assistant"):
            st.markdown(agent_response)
        st.session_state.messages.append({"role": "assistant", "content": agent_response})
else:
    st.info("Please enter your API Key and upload credentials.json, then click 'Start Chat'.")