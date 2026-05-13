"""
Based off demo in https://docs.streamlit.io/develop/tutorials/chat-and-llm-apps/build-conversational-apps
"""

import streamlit as st
from src.assessment_server import AssessmentServer
from src.chat import (
    handle_intro_chat,
    handle_question,
    handle_student_message,
    handle_lm_student_response,
    handle_proctor_response,
    handle_proctor_preparation,
    handle_evaluator_response,
    handle_question_grading,
    handle_chapter_summary,
    handle_test_summary,
)
from outlines.inputs import Chat
from typing import Optional, Literal

from src.models import (
    ChapterSummary,
    EvaluatorResponse,
    QuestionGrade,
    Response,
    TestSummary,
)

st.set_page_config(layout="wide")
st.title("Wildfire demo assessment")

# --- Session State Initialization ---


def get_assessment_server():
    if "assessment_server" in st.session_state:
        return st.session_state.assessment_server
    assessment_server = AssessmentServer()
    st.session_state.assessment_server = assessment_server
    return assessment_server


def init_chat_dict():
    return {
        "main_chat": Chat(),
        "student_chat": Chat(),
        "grader_chat": Chat(),
        "evaluator_chat": Chat(),
    }


if "active_question" not in st.session_state:
    st.session_state.active_question = None  # None means greeting/intro

assessment_server = get_assessment_server()

# --- Helper Render Functions ---


def render_greeting():
    st.subheader("Welcome to the Wildfire Assessment")

    if "intro_chat" not in st.session_state:
        st.session_state.intro_chat = init_chat_dict()
        with st.spinner("Proctor is joining..."):
            st.session_state.intro_chat = handle_intro_chat(st.session_state.intro_chat)

    intro_chat = st.session_state.intro_chat

    # Print all non-system messages to chat
    for message in intro_chat["main_chat"].messages:
        if message["role"] == "system":
            continue
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Allow interaction in the intro phase
    if prompt := st.chat_input("Ask about the exam setup...", key="intro_input"):
        # We'll treat intro responses as generic (not Answer or Clarify)
        handle_student_message(intro_chat, prompt)
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.spinner("Proctor is responding..."):
            proctor_res, _ = handle_proctor_response(intro_chat, assessment_server)
        st.rerun()


    st.divider()
    if st.button("Start Assessment", type="primary"):
        st.session_state.active_question = (1, 0)
        st.rerun()


def render_question(chapter: int, q_idx: int):
    chat_dict = assessment_server.get_chat(chapter, q_idx)
    if not chat_dict:
        # Initialize with just question text
        chat_dict = init_chat_dict()
        with st.spinner("Loading question..."):
            chat_dict = handle_question(chat_dict, assessment_server, chapter, q_idx)

    # Print all non-system messages to chat
    for message in chat_dict["main_chat"].messages:
        if message["role"] == "system":
            continue
        with st.chat_message(message["role"]):
            st.markdown(message["content"])


def render_question_eval(chapter: int, q_idx: int):
    eval: QuestionGrade = assessment_server.question_evals.get((chapter, q_idx))
    if eval:
        with st.expander("Question evaluation", expanded=False):
            col1, col2, col3 = st.columns(3)
            col1.metric("Correct", "Yes" if eval.answer_correct else "No")
            col2.metric("Confidence", f"{eval.confidence}/5")
            col3.metric("Thoroughness", f"{eval.thoroughness}/5")
            st.caption(eval.explanation)


def render_evaluator_feedback(chapter: int, q_idx: int):
    if "evaluator_scores" in st.session_state and st.session_state.evaluator_scores:
        latest: EvaluatorResponse = st.session_state.evaluator_scores[-1]
        with st.expander("Evaluator feedback (last turn)", expanded=False):
            col1, col2, col3 = st.columns(3)
            col1.metric("Fairness", f"{latest.fairness_score}/5")
            col2.metric("Info withheld", f"{latest.information_score}/5")
            col3.metric("Explanation required", f"{latest.explanation_score}/5")
            st.caption(latest.reasoning)


# --- Sidebar Navigation ---

with st.sidebar:
    st.header("Navigation")

    if st.button("Intro / Greeting"):
        st.session_state.active_question = None
        st.rerun()

    for ch_idx in range(1, assessment_server.max_chapter + 1):
        chapter_data = assessment_server.get_chapter_data(ch_idx)
        with st.expander(
            f"Chapter {ch_idx}: {chapter_data['title']}",
            expanded=bool(
                st.session_state.active_question
                and st.session_state.active_question[0] == ch_idx
            ),
        ):
            for q_i, q_data in enumerate(chapter_data["questions"]):
                icon = assessment_server.get_question_status_icon(ch_idx, q_i)
                label = f"{icon} Q{q_i+1}: {q_data['concept_description'][:30]}..."
                if st.button(
                    label, key=f"nav_{ch_idx}_{q_i}", use_container_width=True
                ):
                    st.session_state.active_question = (ch_idx, q_i)
                    st.rerun()

    st.divider()
    assessment_type = st.pills(label="Student type:", options=["human", "ai"])
    teacher_mode = st.checkbox(label="Teacher mode")

    if not st.session_state.get("test_ended") and st.button(
        "End test & summarize", type="primary"
    ):
        st.session_state.test_ended = True
        st.rerun()

# --- Main Content Area ---

if st.session_state.get("test_ended"):
    if "test_summary" not in st.session_state:
        with st.spinner("Evaluating remaining answers..."):

            def grade_cb(cd, ch, qi):
                with st.status(f"Grading Chapter {ch} Question {qi+1}..."):
                    handle_question_grading(cd, assessment_server, ch, qi)

            assessment_server.evaluate_remaining_questions(grade_cb)

        with st.spinner("Generating final summaries..."):
            chapter_summaries: list[ChapterSummary] = []
            for ch in assessment_server.attempted_chapters():
                chapter_summaries.append(handle_chapter_summary(assessment_server, ch))
            test_summary: TestSummary = handle_test_summary(chapter_summaries)
            st.session_state.chapter_summaries = chapter_summaries
            st.session_state.test_summary = test_summary

    st.subheader("Final Test Results")
    ts: TestSummary = st.session_state.test_summary
    st.metric("Overall score", f"{ts.overall_score}/5")
    st.write(ts.summary)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Strengths**")
        for s in ts.strengths:
            st.markdown(f"- {s}")
    with col2:
        st.markdown("**Areas for improvement**")
        for a in ts.areas_for_improvement:
            st.markdown(f"- {a}")

    st.divider()
    st.subheader("Chapter Breakdown")
    for cs in st.session_state.chapter_summaries:
        with st.expander(f"Chapter {cs.chapter} — {cs.overall_score}/5"):
            st.write(cs.summary)
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Strengths**")
                for s in cs.strengths:
                    st.markdown(f"- {s}")
            with col2:
                st.markdown("**Weaknesses**")
                for w in cs.weaknesses:
                    st.markdown(f"- {w}")

    st.stop()

if st.session_state.active_question is None:
    render_greeting()
else:
    chapter, q_idx = st.session_state.active_question
    st.subheader(f"Chapter {chapter} - Question {q_idx + 1}")

    render_question(chapter, q_idx)

    if teacher_mode:
        render_question_eval(chapter, q_idx)
        render_evaluator_feedback(chapter, q_idx)

    # --- Interaction Logic ---

    chat_dict = assessment_server.get_chat(chapter, q_idx)

    def reset_response_selection():
        st.session_state.response_selection = None

    def get_user_response_type() -> (
        Optional[Literal["Answer", "Ask for clarification"]]
    ):
        q_status = assessment_server.get_question_status(chapter, q_idx)

        rem_attempts = assessment_server.remaining_attempts(chapter, q_idx)
        rem_clari = assessment_server.remaining_clarifications(chapter, q_idx)

        answer_label = (
            f"Answer ({rem_attempts}/{assessment_server.max_answer_attempts})"
        )
        clarify_label = f"Clarify ({rem_clari}/{assessment_server.max_clarifications})"

        if q_status == "attempts_and_clarifications":
            raw = st.pills(
                "Response type",
                [answer_label, clarify_label],
                key=f"pills_{chapter}_{q_idx}",
            )
        elif q_status == "no_clarifications":
            raw = st.pills(
                "Response type", [answer_label], key=f"pills_{chapter}_{q_idx}"
            )
        elif q_status == "no_attempts":
            st.warning("Max attempts reached. Please move to the next question.")
            return None
        else:
            return None

        if raw == answer_label:
            return "Answer"
        if raw == clarify_label:
            return "Ask for clarification"
        return None

    if assessment_type == "ai":
        if st.button("Get student answer", key=f"ai_btn_{chapter}_{q_idx}"):
            with st.spinner("Student is thinking..."):
                chat_dict, decision = handle_lm_student_response(
                    chat_dict, assessment_server, chapter, q_idx
                )
                proctor_res, chat_dict = handle_proctor_response(
                    chat_dict, assessment_server, chapter, q_idx
                )

                eval_type = "answer" if decision == "Answer" else "clarify"
                chat_dict, evaluation = handle_evaluator_response(
                    chat_dict, assessment_server, eval_type
                )

                if "evaluator_scores" not in st.session_state:
                    st.session_state.evaluator_scores = []
                st.session_state.evaluator_scores.append(evaluation)
                st.rerun()
    else:
        user_response_type = get_user_response_type()
        if prompt := st.chat_input(
            "Your response...",
            disabled=not user_response_type,
            key=f"input_{chapter}_{q_idx}",
        ):
            full_prompt = f"({user_response_type}) {prompt}"

            # Eagerly display student message
            with st.chat_message("user"):
                st.markdown(full_prompt)
            handle_student_message(chat_dict, full_prompt)

            # Eagerly display status message
            chat_dict, status = handle_proctor_preparation(
                chat_dict, assessment_server, user_response_type, chapter, q_idx
            )
            with st.chat_message("assistant"):
                st.markdown(status)

            with st.spinner("Proctor is responding..."):
                proctor_res, chat_dict = handle_proctor_response(
                    chat_dict, assessment_server, chapter, q_idx
                )

                eval_type = "answer" if user_response_type == "Answer" else "clarify"
                chat_dict, evaluation = handle_evaluator_response(
                    chat_dict, assessment_server, eval_type
                )

                if "evaluator_scores" not in st.session_state:
                    st.session_state.evaluator_scores = []
                st.session_state.evaluator_scores.append(evaluation)
            st.rerun()

    # Next Question button logic
    def get_next_indices(ch, q_i):
        chapter_data = assessment_server.get_chapter_data(ch)
        if q_i + 1 < len(chapter_data["questions"]):
            return (ch, q_i + 1)
        if ch + 1 <= assessment_server.max_chapter:
            return (ch + 1, 0)
        return "end_test"

    next_indices = get_next_indices(chapter, q_idx)
    if next_indices != "end_test":
        if st.button("Next Question ➡️", use_container_width=True):
            st.session_state.active_question = next_indices
            st.rerun()
    else:
        if st.button("Finish Assessment 🏁", type="primary", use_container_width=True):
            st.session_state.test_ended = True
            st.rerun()
