"""
Based off demo in https://docs.streamlit.io/develop/tutorials/chat-and-llm-apps/build-conversational-apps
"""

import streamlit as st
from chat import (
    QuestionServer,
    EvaluatorResponse,
    QuestionGrade,
    ChapterSummary,
    TestSummary,
    Response,
    handle_proctor_greeting,
    handle_next_question,
    handle_student_response,
    handle_lm_student_response,
    handle_proctor_response,
    handle_evaluator_response,
    handle_question_grading,
    handle_chapter_summary,
    handle_test_summary,
)
from outlines.inputs import Chat
from typing import Optional, Literal

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
    chat_dict = {
        "main_chat": Chat(),
        "student_chat": Chat(),
        "grader_chat": Chat(),
        "evaluator_chat": Chat(),
    }

    chat_dict = handle_proctor_greeting(chat_dict, st.session_state.question_server)
    st.session_state.chat_dict = chat_dict
    return chat_dict


def reset_response_selection():
    st.session_state.response_selection = None


def get_user_response_type() -> Optional[Literal["Answer", "Ask for clarification"]]:
    chat_dict: Chat = st.session_state.chat_dict
    question_server: QuestionServer = st.session_state.question_server
    question_status = question_server.get_question_status()

    answer_label = f"Answer ({question_server.remaining_attempts()}/{question_server.max_answer_attempts})"
    clarify_label = f"Ask for clarification ({question_server.remaining_clarifications()}/{question_server.max_clarifications})"

    if question_status == "attempts_and_clarifications":
        raw = st.pills(
            label="Response type",
            options=[answer_label, clarify_label],
            default=None,
            key="response_selection",
        )
    elif question_status == "no_clarifications":
        raw = st.pills(
            label="Response type",
            options=[answer_label],
            key="response_selection",
        )
    elif question_status == "no_attempts":
        chat_dict, _ = handle_question_grading(chat_dict, question_server)
        st.session_state.chat_dict = chat_dict
        handle_next_question(chat_dict, question_server)
        user_response_type = None
        st.rerun()
    else:
        raise ValueError("Unrecognized question status", question_status)

    # map label back to canonical type
    if raw == answer_label:
        user_response_type = "Answer"
    elif raw == clarify_label:
        user_response_type = "Ask for clarification"
    else:
        user_response_type = None

    # cache user response type so resetting button doesn't change it
    if user_response_type:
        st.session_state.last_response_type = user_response_type
    elif st.session_state.get("last_response_type", None) is not None:
        return st.session_state.last_response_type
    return user_response_type


get_question_server()
get_chat()

# progress bars
question_server: QuestionServer = st.session_state.question_server
if question_server.question_index >= 0:
    chapter_data = question_server.get_current_chapter_data()
    total_questions = len(chapter_data["questions"])
    q_done = question_server.question_index + 1
    st.progress(
        q_done / total_questions,
        text=f"Question {q_done} of {total_questions} in chapter {question_server.chapter_index}",
    )
    st.progress(
        question_server.chapter_index / question_server.max_chapter,
        text=f"Chapter {question_server.chapter_index} of {question_server.max_chapter}",
    )

# end test early button
if not st.session_state.get("test_ended") and st.button(
    "End test early", type="secondary"
):
    st.session_state.test_ended = True

if st.session_state.get("test_ended"):
    if "test_summary" not in st.session_state:
        with st.spinner("Generating results..."):
            qs: QuestionServer = st.session_state.question_server
            chapter_summaries: list[ChapterSummary] = []
            for ch in qs.attempted_chapters():
                chapter_summaries.append(handle_chapter_summary(qs, ch))
            test_summary: TestSummary = handle_test_summary(chapter_summaries)
            st.session_state.chapter_summaries = chapter_summaries
            st.session_state.test_summary = test_summary

    st.subheader("Test Results")

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

# display question eval from previous question, if any
if teacher_mode and question_server.question_evals:
    chapter_index = question_server.last_chapter_attempted()
    latest_eval: QuestionGrade = question_server.question_evals[chapter_index][-1]
    with st.expander("Question eval (last question)"):
        col1, col2, col3 = st.columns(3)
        col1.metric("Correct", "Yes" if latest_eval.answer_correct else "No")
        col2.metric("Confidence", f"{latest_eval.confidence}/5")
        col3.metric("Thoroughness", f"{latest_eval.thoroughness}/5")
        st.caption(latest_eval.explanation)

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

        # rerun app so messages will be printed, as handled above
        st.rerun()
