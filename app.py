"""
Wildfire Assessment - Streamlit Frontend
Stateless version using AssessmentServer.
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
    handle_question_grading,
    handle_chapter_summary,
    handle_test_summary,
    get_system_prompt,
)
from outlines.inputs import Chat
from typing import Optional, Literal, List

from src.models import (
    ChapterSummary,
    QuestionGrade,
    Response,
    TestSummary,
    Question,
    QuestionAttempt,
    Chapter,
)

st.set_page_config(layout="wide", page_title="Wildfire Assessment")
st.title("Wildfire demo assessment")

# --- Session State Initialization ---


@st.cache_resource
def get_assessment_server():
    server = AssessmentServer()
    server.init_db()
    return server


server: AssessmentServer = get_assessment_server()

if "assessment_id" not in st.session_state:
    # Optional: Start with a new assessment automatically or wait for code
    if "auto_start" not in st.session_state:
        st.session_state.assessment_id, st.session_state.exam_code = (
            server.create_assessment()
        )
        st.session_state.auto_start = True

if "active_question" not in st.session_state:
    st.session_state.active_question = None  # None means greeting/intro

# --- Helper Render Functions ---


def get_user_response_type(
    server: AssessmentServer, attempt: QuestionAttempt
) -> Optional[Literal["Answer", "Ask for clarification"]]:
    rem_attempts = server.max_answer_attempts - attempt.num_answer_attempts
    rem_clari = server.max_clarifications - attempt.num_clarifications

    if rem_attempts <= 0:
        st.warning("Max attempts reached.")
        return None

    answer_label = f"Answer ({rem_attempts}/{server.max_answer_attempts})"
    clarify_label = f"Clarify ({rem_clari}/{server.max_clarifications})"

    options = [answer_label]
    if rem_clari > 0:
        options.append(clarify_label)

    raw = st.pills("Response type", options, key=f"pills_{attempt.id}")

    if raw == answer_label:
        return "Answer"
    if raw == clarify_label:
        return "Ask for clarification"
    return None


def render_greeting():
    st.subheader("Welcome to the Wildfire Assessment")
    st.info(f"Your Exam Code: **{st.session_state.get('exam_code', 'N/A')}**")

    # Ephemeral intro chat
    if "intro_chat" not in st.session_state:
        with st.spinner("Proctor is joining..."):
            st.session_state.intro_chat = handle_intro_chat(
                server, st.session_state.assessment_id
            )

    intro_chat: Chat = st.session_state.intro_chat

    # Print messages
    for message in intro_chat.messages:
        if message["role"] == "system":
            continue
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Generic interaction (not persisted in this demo for intro)
    if prompt := st.chat_input("Ask about the exam setup...", key="intro_input"):
        intro_chat.add_user_message(prompt)
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.spinner("Proctor is responding..."):
            # Simple ephemeral response for intro
            response = handle_proctor_response(server, is_question=False)
            intro_chat.add_assistant_message(response.message)
        st.rerun()

    st.divider()
    if st.button("Start Assessment", type="primary"):
        st.session_state.active_question = (1, 0)  # Chapter 1, Question 0
        st.rerun()


def render_question(attempt_id: int, question: Question):
    # Display question text prominently at the top
    st.markdown(f"**Question:**\n{question.question_text}")
    st.divider()

    prompt = get_system_prompt("proctor", "base")
    chat = server.load_chat_for_llm(attempt_id, prompt, role="proctor")

    # Initialize if needed
    if len(chat.messages) <= 1:
        with st.spinner("Loading question..."):
            chat = handle_question(server, attempt_id, question)

    # Print chat messages
    for message in chat.messages:
        if message["role"] == "system":
            continue
        # outlines.inputs.Chat roles are 'user', 'assistant', 'system'
        with st.chat_message(message["role"]):
            st.markdown(message["content"])


def render_question_eval(attempt_id: int):
    # Fetch from server (stateless)
    from sqlmodel import Session, select

    with Session(server.engine) as session:
        attempt = session.get(QuestionAttempt, attempt_id)
        if attempt and attempt.grade_data:
            eval = QuestionGrade.model_validate(attempt.grade_data)
            with st.expander("Question evaluation", expanded=False):
                col1, col2, col3 = st.columns(3)
                col1.metric("Correct", "Yes" if eval.answer_correct else "No")
                col2.metric("Confidence", f"{eval.confidence}/5")
                col3.metric("Thoroughness", f"{eval.thoroughness}/5")
                st.caption(eval.explanation)


# --- Sidebar Navigation ---

with st.sidebar:
    st.header("Navigation")

    if st.button("Intro / Greeting"):
        st.session_state.active_question = None
        st.rerun()

    # Get chapters from DB
    from sqlmodel import Session, select

    with Session(server.engine) as session:
        chapters = session.exec(select(Chapter).order_by(Chapter.id)).all()
        for ch in chapters:
            with st.expander(
                f"Chapter {ch.id}: {ch.title}",
                expanded=bool(
                    st.session_state.active_question
                    and st.session_state.active_question[0] == ch.id
                ),
            ):
                for q_idx, q in enumerate(ch.questions):
                    # Check status (stateless)
                    attempt = server.get_or_create_attempt(
                        st.session_state.assessment_id, q.id
                    )
                    icon = server.get_question_status_icon(attempt)

                    label = f"{icon} Q{q_idx + 1}: {q.concept_description[:30]}..."
                    if st.button(
                        label,
                        key=f"nav_{ch.id}_{q_idx}",
                        use_container_width=True,
                    ):
                        st.session_state.active_question = (ch.id, q_idx)
                        st.rerun()

    st.divider()
    assessment_type = st.pills(
        label="Student type:", options=["human", "ai"], default="human"
    )
    teacher_mode = st.checkbox(label="Teacher mode")

    if not st.session_state.get("test_ended") and st.button(
        "End test & summarize", type="primary"
    ):
        st.session_state.test_ended = True
        st.rerun()

# --- Main Content Area ---

if st.session_state.get("test_ended"):
    from sqlmodel import Session, select, and_

    # 1. Grade ungraded attempts
    ungraded = server.get_ungraded_attempts(st.session_state.assessment_id)
    if ungraded:
        with st.status("Grading remaining questions...") as status:
            for att in ungraded:
                st.write(f"Grading Chapter {att.question.chapter_id} Question...")
                handle_question_grading(server, att.id)
            status.update(label="Grading complete!", state="complete")

    # 2. Generate Chapter Summaries
    chapters = server.get_attempted_chapters(st.session_state.assessment_id)
    chapter_summaries = []

    for i, ch in enumerate(chapters):
        with st.status(f"Generating summary for chapter {i+1}...") as status:
            ch_attempt = server.get_or_create_chapter_attempt(
                st.session_state.assessment_id, ch.id
            )
            if not ch_attempt.summary_data:
                st.write(f"Summarizing Chapter {ch.id}: {ch.title}...")
                with Session(server.engine) as session:
                    db_ch = session.get(Chapter, ch.id)
                    stmt = (
                        select(QuestionAttempt)
                        .join(Question)
                        .where(
                            and_(
                                QuestionAttempt.assessment_id
                                == st.session_state.assessment_id,
                                Question.chapter_id == ch.id,
                                QuestionAttempt.grade_data.is_not(None),
                            )
                        )
                    )
                    attempts = session.exec(stmt).all()

                    summary = handle_chapter_summary(
                        server, ch_attempt.id, ch.title, db_ch.questions, attempts
                    )
            else:
                summary = ChapterSummary.model_validate(ch_attempt.summary_data)
            chapter_summaries.append(summary)
        status.update(label="Chapter summaries complete!", state="complete")

    # 3. Generate Test Summary
    with Session(server.engine) as session:
        db_ass = session.get(Assessment, st.session_state.assessment_id)
        if not db_ass.test_summary:
            with st.spinner("Generating final test summary..."):
                test_summary = handle_test_summary(server, db_ass.id, chapter_summaries)
        else:
            test_summary = TestSummary.model_validate(db_ass.test_summary)

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
    ch_id, q_idx = st.session_state.active_question
    question = server.get_question(ch_id, q_idx)

    if not question:
        st.error(f"Question not found: Chapter {ch_id}, Index {q_idx}")
        if st.button("Home"):
            st.session_state.active_question = None
            st.rerun()
        st.stop()

    attempt = server.get_or_create_attempt(st.session_state.assessment_id, question.id)

    st.subheader(f"Chapter {ch_id} - Question {q_idx + 1}")
    render_question(attempt.id, question)

    if teacher_mode:
        render_question_eval(attempt.id)

    # --- Interaction Logic ---

    if assessment_type == "ai":
        if st.button("Get student answer", key=f"ai_btn_{attempt.id}"):
            with st.spinner("Student is thinking..."):
                handle_lm_student_response(server, attempt.id)
                handle_proctor_response(server, attempt.id)
                st.rerun()
    else:
        user_response_type = get_user_response_type(server, attempt)
        if prompt := st.chat_input(
            "Your response...",
            disabled=not user_response_type,
            key=f"input_{attempt.id}",
        ):
            full_prompt = f"({user_response_type}) {prompt}"

            # Persist and Respond
            handle_student_message(server, attempt.id, full_prompt)
            handle_proctor_preparation(server, attempt.id, user_response_type)

            with st.spinner("Proctor is responding..."):
                handle_proctor_response(server, attempt.id)
                st.rerun()
