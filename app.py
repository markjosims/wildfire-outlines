"""
Based off demo in https://docs.streamlit.io/develop/tutorials/chat-and-llm-apps/build-conversational-apps
"""

import streamlit as st
from chat import (
    QuestionServer,
    EvaluatorResponse,
    Response,
    handle_proctor_greeting,
    handle_next_question,
    handle_student_response,
    handle_lm_student_response,
    handle_proctor_response,
    handle_evaluator_response,
)
from outlines.inputs import Chat
from typing import Optional, Literal
# import os

# uncomment to allow setting assessment type in environment
# for now use Streamlit toggle
# assessment_type: Literal["human", "ai"] = os.getenv("ASSESSMENT_TYPE", "human")

st.title("Wildfire demo assessment")

assessment_type = st.pills(label="Student type:", options=["human", "ai"])

teacher_mode = st.checkbox(label="Teacher mode")


def get_question_server():
    if "question_server" in st.session_state:
        return st.session_state.question_server
    question_server = QuestionServer()
    st.session_state.question_server = question_server
    return question_server


def get_chat():
    if "chat_dict" in st.session_state:
        return st.session_state.chat_dict

    # for now appending all chats regardless of assessment_type
    # that way user can easily toggle AI response on and off
    chat_dict = {"main_chat": Chat(), "student_chat": Chat(), "evaluator_chat": Chat()}

    chat_dict = handle_proctor_greeting(chat_dict, st.session_state.question_server)
    st.session_state.chat_dict = chat_dict
    return chat_dict


def reset_response_selection():
    st.session_state.response_selection = None


def get_user_response_type() -> Optional[Literal["Answer", "Ask for clarification"]]:
    chat_dict: Chat = st.session_state.chat_dict
    question_server: QuestionServer = st.session_state.question_server
    question_status = question_server.get_question_status()
    if question_status == "attempts_and_clarifications":
        user_response_type = st.pills(
            label="Response type",
            options=["Answer", "Ask for clarification"],
            default=None,
            # disabled=st.session_state.get("reset_response_selection", False),
            key="response_selection",
        )
    elif question_status == "no_clarifications":
        user_response_type = st.pills(
            label="Response type",
            options=["Answer"],
            # disabled=st.session_state.get("reset_response_selection", False),
            key="response_selection",
        )
    elif question_status == "no_attempts":
        handle_next_question(chat_dict, question_server)
        user_response_type = None
        st.rerun()
    else:
        raise ValueError("Unrecognized question status", question_status)

    # cache user response type so resetting button doesn't change it
    if user_response_type:
        st.session_state.last_response_type = user_response_type
    elif st.session_state.get("last_response_type", None) is not None:
        return st.session_state.last_response_type
    return user_response_type


get_question_server()
get_chat()

# print all non-system messages to chat
for message in st.session_state.chat_dict["main_chat"].messages:
    if message["role"] == "system":
        continue
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# display proctor response from previous turn, if any
# for now do this both in AI and human mode
# at production time this will need to be hidden from the student
if (
    teacher_mode
    and "proctor_response_list" in st.session_state
    and st.session_state.proctor_response_list
):
    latest_response: Response = st.session_state.proctor_response_list[-1]
    with st.expander("Proctor response"):
        st.metric("Decision", latest_response.decision)
        st.caption(latest_response.reasoning)

# display evaluator scores from previous turn, if any
if (
    teacher_mode
    and "evaluator_scores" in st.session_state
    and st.session_state.evaluator_scores
):
    latest: EvaluatorResponse = st.session_state.evaluator_scores[-1]
    with st.expander("Evaluator scores (last proctor turn)"):
        col1, col2, col3 = st.columns(3)
        col1.metric("Fairness", f"{latest.fairness_score}/5")
        col2.metric("Info withheld", f"{latest.information_score}/5")
        col3.metric("Explanation required", f"{latest.explanation_score}/5")
        st.caption(latest.reasoning)

# get ai student response, if applicable
if assessment_type == "ai":
    chat_dict = st.session_state.chat_dict
    question_server = st.session_state.question_server
    # wait for user input before getting student model answer
    if st.button("Get student answer"):
        st.write("Loading answer...")
        chat_dict, student_decision = handle_lm_student_response(
            chat_dict, question_server
        )
        proctor_response, chat_dict = handle_proctor_response(
            chat_dict, question_server
        )

        if "proctor_response_list" not in st.session_state:
            st.session_state.proctor_response_list = []
        st.session_state.proctor_response_list.append(proctor_response)

        evaluator_prompt_type = "answer" if student_decision == "Answer" else "clarify"
        chat_dict, evaluation = handle_evaluator_response(
            chat_dict, question_server, evaluator_prompt_type
        )

        if "evaluator_scores" not in st.session_state:
            st.session_state.evaluator_scores = []
        st.session_state.evaluator_scores.append(evaluation)
        st.session_state.chat_dict = chat_dict

        st.rerun()


# get user's response to assistant's last message
# user must select response type before chat will be enabled
else:
    # allow user to choose between "answer" and "ask for clarification"
    # based on previous question
    user_response_type = get_user_response_type()

    if prompt := st.chat_input(
        "Type response here",
        disabled=not user_response_type,
        on_submit=reset_response_selection,
    ):
        assert user_response_type is not None
        # prepend response type to prompt for transparency when printed to chat
        prompt = f"({user_response_type}) {prompt}"

        chat_dict = st.session_state.chat_dict
        question_server = st.session_state.question_server
        handle_student_response(chat_dict, user_response_type, question_server, prompt)

        with st.chat_message("user"):
            st.markdown(prompt)

        # reset last response type as we no longer need it
        st.session_state.last_response_type = None

    # give user prompt to assistant and let assistant decide to follow up
    # or ask next question
    if prompt:
        chat_dict = st.session_state.chat_dict
        question_server = st.session_state.question_server
        proctor_response, chat_dict = handle_proctor_response(
            chat_dict, question_server
        )

        if "proctor_response_list" not in st.session_state:
            st.session_state.proctor_response_list = []
        st.session_state.proctor_response_list.append(proctor_response)

        evaluator_prompt_type = (
            "answer" if user_response_type == "Answer" else "clarify"
        )
        chat_dict, evaluation = handle_evaluator_response(
            chat_dict, question_server, evaluator_prompt_type
        )

        if "evaluator_scores" not in st.session_state:
            st.session_state.evaluator_scores = []
        st.session_state.evaluator_scores.append(evaluation)
        st.session_state.chat_dict = chat_dict

        st.session_state.chat_dict = chat_dict

        # rerun app so messages will be printed, as handled above
        st.rerun()
