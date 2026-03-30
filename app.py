"""
Based off demo in https://docs.streamlit.io/develop/tutorials/chat-and-llm-apps/build-conversational-apps
"""

from re import A
import streamlit as st
from chat import (
    QuestionServer,
    handle_assistant_greeting,
    handle_next_question,
    handle_student_response,
    handle_assistant_response,
)
from outlines.inputs import Chat
from typing import Optional, Literal

st.title("Wildfire demo assessment")


def get_question_server():
    if "question_server" in st.session_state:
        return st.session_state.question_server
    question_server = QuestionServer()
    st.session_state.question_server = question_server
    return question_server


def get_chat():
    if "chat" in st.session_state:
        return st.session_state.chat
    chat = Chat()
    chat = handle_assistant_greeting(chat, st.session_state.question_server)
    st.session_state.chat = chat
    return chat


def get_user_response_type() -> Optional[Literal["Answer", "Ask for clarification"]]:
    chat: Chat = st.session_state.chat
    question_server: QuestionServer = st.session_state.question_server
    question_status = question_server.get_question_status()
    if question_status == "attempts_and_clarifications":
        user_response_type = st.pills(
            label="Response type", options=["Answer", "Ask for clarification"]
        )
    elif question_status == "no_clarifications":
        user_response_type = st.pills(
            label="Response type", options=["Answer"], default="Answer"
        )
    elif question_status == "no_attempts":
        handle_next_question(chat, question_server)
        user_response_type = None
        st.rerun()
    else:
        raise ValueError(f"Unrecognized question status", question_status)
    return user_response_type


get_question_server()
get_chat()

# print all non-system messages to chat
for message in st.session_state.chat.messages:
    if message["role"] == "system":
        continue
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# allow user to choose between "answer" and "ask for clarification"
# based on previous question
user_response_type = get_user_response_type()

# get user's response to assistant's last message
# user must select response type before chat will be enabled
if prompt := st.chat_input("Type response here", disabled=not user_response_type):
    # prepend response type to prompt for transparency when printed to chat
    prompt = f"({user_response_type}) {prompt}"

    chat = st.session_state.chat
    question_server = st.session_state.question_server
    handle_student_response(chat, user_response_type, question_server, prompt)

    with st.chat_message("user"):
        st.markdown(prompt)

# give user prompt to assistant and let assistant decide to follow up
# or ask next question
if prompt:
    chat = st.session_state.chat
    chat = handle_assistant_response(chat, st.session_state.question_server)

    st.session_state.chat = chat
    # rerun app so messages will be printed, as handled above
    st.rerun()
