"""
Wildfire Assessment - Streamlit Frontend
Stateless version using AssessmentServer.
"""

import streamlit as st
import os
from src.assessment_server import AssessmentServer
from src.chat import (
    handle_intro_chat,
    handle_question,
    handle_student_message,
    handle_lm_student_response,
    handle_proctor_response_decision,
    handle_proctor_student_response,
    handle_proctor_preparation,
    handle_question_grading,
    handle_chapter_summary,
    handle_test_summary,
    get_system_prompt,
)
from outlines.inputs import Chat
from sqlmodel import Session, select, and_
from typing import Optional
from typing_extensions import Literal

from src.models import (
    ChapterSummary,
    QuestionGrade,
    TestSummary,
    Question,
    QuestionAttempt,
    Chapter,
    Assessment,
)

st.set_page_config(layout="wide", page_title="Wildfire Assessment")
st.title("Wildfire demo assessment")

# --- Session State Initialization ---


@st.cache_resource
def get_assessment_server():
    """
    Load `AssessmentServer` and initialize database.
    """
    server = AssessmentServer()
    server.init_db()
    return server


server: AssessmentServer = get_assessment_server()

# --- Session State Initialization ---

if "assessment_id" not in st.session_state:
    st.session_state.assessment_id = None
    st.session_state.exam_code = None

if "active_question" not in st.session_state:
    st.session_state.active_question = None

# --- Global Header ---

if st.session_state.exam_code:
    st.info(f"Exam Code: **{st.session_state.exam_code}**")

# --- Splash Page / Entry Logic ---


def render_splash():
    st.subheader("Get Started")
    col1, col2 = st.columns(2)

    with col1:
        st.write("### New Assessment")
        if st.button("Generate New Exam Code", type="primary", use_container_width=True):
            id, code = server.create_assessment()
            st.session_state.assessment_id = id
            st.session_state.exam_code = code
            st.rerun()

    with col2:
        st.write("### Resume Assessment")
        code_input = st.text_input("Enter your Exam Code (e.g., AB-12-CD)")
        if st.button("Resume", use_container_width=True):
            if code_input:
                assessment = server.get_assessment_by_code(code_input.upper())
                if assessment:
                    st.session_state.assessment_id = assessment.id
                    st.session_state.exam_code = assessment.exam_code
                    st.rerun()
                else:
                    st.error("Invalid Exam Code. Please check and try again.")
            else:
                st.warning("Please enter a code.")


# --- Main Flow ---

if st.session_state.assessment_id is None:
    render_splash()
    st.stop()

# --- Helper Render Functions ---


def get_user_response_type(
    server: AssessmentServer, attempt: QuestionAttempt
) -> Optional[Literal["Answer", "Ask for clarification"]]:
    """
    Provides UI for retrieving user response type. Each user turn in a
    question chat may be an answer attempt or a request for clarification.
    The AssessmentServer provides a limited number of answer attempts or
    clarification requests, so the widget is disabled if the maximum for a
    type is reached.
    """
    remaining_attempts = server.max_answer_attempts - attempt.num_answer_attempts
    remaining_clarifications = server.max_clarifications - attempt.num_clarifications

    if remaining_attempts <= 0:
        st.warning("Max attempts reached.")
        return None

    answer_label = f"Answer ({remaining_attempts}/{server.max_answer_attempts})"
    clarify_label = f"Clarify ({remaining_clarifications}/{server.max_clarifications})"

    options = [answer_label]
    if remaining_clarifications > 0:
        options.append(clarify_label)

    raw = st.pills("Response type", options, key=f"pills_{attempt.id}")

    if raw == answer_label:
        return "Answer"
    if raw == clarify_label:
        return "Ask for clarification"
    return None


def render_greeting():
    """
    Display intro chat with LLM proctor.
    """
    st.subheader("Welcome to the Wildfire Assessment")

    # Ephemeral intro chat
    if "intro_chat" not in st.session_state:
        with st.spinner("Proctor is joining..."):
            st.session_state.intro_chat = handle_intro_chat()

    intro_chat: Chat = st.session_state.intro_chat

    # Print messages
    for message in intro_chat.messages:
        if message["role"] == "system":
            continue
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if "pending_intro_decision" in st.session_state:
        decision = st.session_state["pending_intro_decision"]
        with st.chat_message("assistant"):
            full_response = st.write_stream(
                handle_proctor_student_response(server, None, decision)
            )
            intro_chat.add_assistant_message(str(full_response))
        del st.session_state["pending_intro_decision"]
        st.rerun()

    elif "pending_intro_decision" not in st.session_state:
        prompt = st.chat_input("Ask about the exam setup...", key="intro_input")
        if prompt:
            intro_chat.add_user_message(prompt)
            with st.chat_message("user"):
                st.markdown(prompt)

            with st.spinner("Proctor is thinking..."):
                decision = handle_proctor_response_decision(server)
                st.session_state["pending_intro_decision"] = decision

            st.rerun()

    st.divider()
    if st.button("Start Assessment", type="primary"):
        st.session_state.active_question = (1, 0)  # Chapter 1, Question 0
        st.rerun()


def render_question(attempt_id: int, question: Question, server: AssessmentServer):
    """
    Render question text and chat history pertinent to a given question.
    """
    # Display question text prominently at the top
    st.markdown(server.format_question(question))
    st.divider()

    prompt = get_system_prompt("proctor", "base")
    chat = server.load_chat_for_llm(attempt_id, prompt, role="proctor")

    # Initialize if needed
    if len(chat.messages) <= 1:
        with st.spinner("Loading question..."):
            chat = handle_question(server, attempt_id)

    # Print chat messages
    for message in chat.messages:
        if message["role"] == "system":
            continue
        # outlines.inputs.Chat roles are 'user', 'assistant', 'system'
        with st.chat_message(message["role"]):
            st.markdown(message["content"])


def render_question_eval(attempt_id: int):
    """
    Render grade output by Grader LLM if question attempt exists and is completed.
    """
    # Fetch from server (stateless)

    with Session(server.engine) as session:
        attempt = session.get(QuestionAttempt, attempt_id)
        if attempt and attempt.grade_data:
            grade = QuestionGrade.model_validate(attempt.grade_data)
            with st.expander("Question evaluation", expanded=False):
                col1, col2, col3 = st.columns(3)
                col1.metric("Correct", "Yes" if grade.answer_correct else "No")
                col2.metric("Confidence", f"{grade.confidence}/5")
                col3.metric("Thoroughness", f"{grade.thoroughness}/5")
                st.caption(grade.explanation)


# --- Sidebar Navigation ---

with st.sidebar:
    st.header("Navigation")

    if st.button("Intro / Greeting"):
        st.session_state.active_question = None
        st.rerun()

    # Get chapters from DB

    with Session(server.engine) as session:
        chapters = session.exec(select(Chapter).order_by(Chapter.id)).all()
        for chapter in chapters:
            with st.expander(
                f"Chapter {chapter.id}: {chapter.title}",
                expanded=bool(
                    st.session_state.active_question
                    and st.session_state.active_question[0] == chapter.id
                ),
            ):
                for question_idx, question in enumerate(chapter.questions):
                    # Check status (stateless)
                    attempt = server.get_or_create_attempt(
                        st.session_state.assessment_id, question.id
                    )
                    icon = server.get_question_status_icon(attempt)

                    label = f"{icon} Q{question_idx + 1}: {question.concept_description[:30]}..."
                    if st.button(
                        label,
                        key=f"nav_{chapter.id}_{question_idx}",
                        use_container_width=True,
                    ):
                        st.session_state.active_question = (chapter.id, question_idx)
                        st.rerun()

    if int(os.environ.get("TEACHER_MODE_ENABLED", 0)):
        st.divider()
        st.pills(
            label="Student type:",
            options=["human", "ai"],
            default="human",
            key="assessment_type",
        )
        st.checkbox(label="Teacher mode", key="teacher_mode")

    if not st.session_state.get("test_ended") and st.button(
        "End test & summarize", type="primary"
    ):
        st.session_state.test_ended = True
        st.rerun()

# --- Main Content Area ---

if st.session_state.get("test_ended"):
    # 1. Grade ungraded attempts
    ungraded = server.get_ungraded_attempts(st.session_state.assessment_id)
    if ungraded:
        with st.status("Grading remaining questions...") as status:
            for att in ungraded:
                st.write(f"Grading Chapter {att.question.chapter_id} Question...")
                assert type(att.id) is int
                handle_question_grading(server, att.id)
            status.update(label="Grading complete!", state="complete")

    # 2. Generate Chapter Summaries
    chapters = server.get_attempted_chapters(st.session_state.assessment_id)
    chapter_summaries = []

    for i, chapter in enumerate(chapters):
        with st.status(f"Generating summary for chapter {i + 1}...") as status:
            chapter_attempt = server.get_or_create_chapter_attempt(
                st.session_state.assessment_id, chapter.id
            )
            if not chapter_attempt.summary_data:
                st.write(f"Summarizing Chapter {chapter.id}: {chapter.title}...")
                with Session(server.engine) as session:
                    db_ch = session.get(Chapter, chapter.id)
                    stmt = (
                        select(QuestionAttempt)
                        .join(Question)
                        .where(
                            and_(
                                QuestionAttempt.assessment_id
                                == st.session_state.assessment_id,
                                Question.chapter_id == chapter.id,
                                QuestionAttempt.grade_data.is_not(None),  # type: ignore
                            )
                        )
                    )
                    attempts = session.exec(stmt).all()

                    assert chapter_attempt.id is not None
                    summary = handle_chapter_summary(
                        server,
                        chapter_attempt.id,
                        chapter.title,
                        db_ch.questions,
                        attempts,
                    )
            else:
                summary = ChapterSummary.model_validate(chapter_attempt.summary_data)
            chapter_summaries.append(summary)
        status.update(label="Chapter summaries complete!", state="complete")

    # 3. Generate Test Summary
    with Session(server.engine) as session:
        assessment = session.get(Assessment, st.session_state.assessment_id)
        if not assessment.test_summary:
            with st.spinner("Generating final test summary..."):
                test_summary = handle_test_summary(
                    server, assessment.id, chapter_summaries
                )
        else:
            test_summary = TestSummary.model_validate(assessment.test_summary)

    # 4. Render Results
    st.subheader("Final Test Results")
    st.metric("Overall score", f"{test_summary.overall_score}/5")
    st.write(test_summary.summary)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Strengths**")
        for s in test_summary.strengths:
            st.markdown(f"- {s}")
    with col2:
        st.markdown("**Areas for improvement**")
        for a in test_summary.areas_for_improvement:
            st.markdown(f"- {a}")

    st.divider()
    st.subheader("Chapter Breakdown")
    for cs in chapter_summaries:
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

    if st.button("Back to questions"):
        st.session_state.test_ended = False
        st.rerun()
    st.stop()

if st.session_state.active_question is None:
    render_greeting()
else:
    ch_id, question_idx = st.session_state.active_question
    question = server.get_question(ch_id, question_idx)

    if not question:
        st.error(f"Question not found: Chapter {ch_id}, Index {question_idx}")
        if st.button("Home"):
            st.session_state.active_question = None
            st.rerun()
        st.stop()

    assert type(question.id) is int
    attempt = server.get_or_create_attempt(st.session_state.assessment_id, question.id)

    assert type(attempt.id) is int
    st.subheader(f"Chapter {ch_id} - Question {question_idx + 1}")
    render_question(attempt.id, question, server)

    if st.session_state.get("teacher_mode", None):
        render_question_eval(attempt.id)

    @st.fragment
    def interaction_logic(attempt_id: int, ch_id: int, question_idx: int):
        # Fetch fresh attempt data for this fragment
        with Session(server.engine) as session:
            attempt = session.get(QuestionAttempt, attempt_id)
            if not attempt:
                return

        pending_key = f"pending_decision_{attempt.id}"
        optimistic_complete_key = f"optimistic_complete_{attempt.id}"

        # Determine if question is complete (optimistic check)
        is_complete = attempt.grade_data is not None or st.session_state.get(
            optimistic_complete_key, False
        )

        # Navigation Button
        next_q = server.get_next_incomplete_question(
            st.session_state.assessment_id, ch_id, question_idx
        )
        if next_q:
            label = (
                "Continue to next question" if is_complete else "Skip to next question"
            )

            _, col = st.columns([4, 1])
            with col:
                if st.button(
                    label,
                    key=f"next_btn_{attempt.id}",
                    use_container_width=True,
                ):
                    st.session_state.active_question = next_q
                    # Clear optimistic flags for the next question
                    if optimistic_complete_key in st.session_state:
                        del st.session_state[optimistic_complete_key]
                    st.rerun(scope="app")

        # Create containers for correct visual ordering
        chat_container = st.container()
        input_container = st.container()

        # Execute input block first so that UI updates (disappearing input, appearing badge)
        # flush to the frontend BEFORE the blocking st.write_stream call.
        with input_container:
            if is_complete:
                st.badge(label="Question complete", icon=":material/check:", color="gray")
            elif st.session_state.get("assessment_type", None) == "ai":
                if st.button("Get student answer", key=f"ai_btn_{attempt.id}"):
                    with st.spinner("Student is thinking..."):
                        handle_lm_student_response(server, attempt.id)

                    with st.spinner("Proctor is thinking..."):
                        decision = handle_proctor_response_decision(server, attempt.id)
                        st.session_state[pending_key] = decision
                        if decision.decision == "question_complete":
                            st.session_state[optimistic_complete_key] = True

                    st.rerun()
            else:
                user_response_type = get_user_response_type(server, attempt)
                prompt = st.chat_input(
                    "Your response...",
                    disabled=not user_response_type,
                    key=f"input_{attempt.id}",
                )
                if prompt:
                    assert user_response_type is not None
                    full_prompt = f"({user_response_type}) {prompt}"

                    # Persist Student Message
                    handle_student_message(server, attempt.id, full_prompt)
                    handle_proctor_preparation(server, attempt.id, user_response_type)

                    with chat_container:
                        with st.chat_message("user"):
                            st.markdown(full_prompt)

                    with st.spinner("Proctor is thinking..."):
                        decision = handle_proctor_response_decision(server, attempt.id)
                        st.session_state[pending_key] = decision
                        if decision.decision == "question_complete":
                            st.session_state[optimistic_complete_key] = True

                    st.rerun()

        # Process pending assistant response (Blocking stream)
        if pending_key in st.session_state:
            decision = st.session_state[pending_key]
            with chat_container:
                with st.chat_message("assistant"):
                    full_response = st.write_stream(
                        handle_proctor_student_response(server, attempt.id, decision)
                    )
                    # Save to DB now that stream is done
                    server.record_message(attempt.id, "assistant", str(full_response))

            if decision.decision == "question_complete":
                handle_question_grading(server, attempt.id)

            del st.session_state[pending_key]
            st.rerun()

    interaction_logic(attempt.id, ch_id, question_idx)
