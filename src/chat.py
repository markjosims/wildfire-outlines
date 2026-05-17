"""
Helper functions for managing assessment chat.
Stateless version using AssessmentServer for persistence.
"""

from openai import OpenAI
from dotenv import load_dotenv
import json
import outlines
from outlines.inputs import Chat
import os
from typing import List, Optional, Union
from typing_extensions import Literal
import logging
from src.assessment_server import AssessmentServer
from src.models import (
    ChapterSummary,
    Greeting,
    QuestionGrade,
    Response,
    StudentAnswer,
    TestSummary,
    Question,
    QuestionAttempt,
)
from secret import get_secret

# configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# get OpenAI environment vars
load_dotenv()
if "OPENAI_API_KEY" not in os.environ:
    os.environ["OPENAI_API_KEY"] = get_secret()


openai_model = os.environ.get("OPENAI_MODEL", "gpt-5.5")
client = OpenAI()
model = outlines.from_openai(client, openai_model)


# Unique roles LLMs may take
RoleType = Literal["proctor", "student", "grader"]

# Main interlocutors
ParticipantType = Literal["proctor", "student", "system"]

# Enumeration of all prompt types stored in prompts/ folder
PromptType = Literal[
    "base",
    "question",
    "clarify",
    "decide-answer-response",
    "give-student-response",
    "grade-question",
    "chapter-summary",
    "test-summary",
]

"""
Prompt functions
"""


def get_system_prompt(
    role: RoleType = "proctor",
    prompt_type: PromptType = "base",
) -> str:
    """
    Retrieve system prompt text for a given role and prompt type.
    """
    system_prompt_path = f"./prompts/{role}/{prompt_type}-prompt.txt"
    with open(system_prompt_path) as f:
        system_prompt = f.read()
    return system_prompt


def handle_question(
    server: AssessmentServer,
    attempt_id: int,
) -> Chat:
    """
    Returns the current proctor chat context.
    Injection of question data is handled by server.load_chat_for_llm.
    """
    prompt = get_system_prompt("proctor", "base")
    chat = server.load_chat_for_llm(attempt_id, prompt, role="proctor")
    return chat


def handle_student_message(
    server: AssessmentServer,
    attempt_id: int,
    content: str,
):
    """Saves student message as 'user'."""
    server.record_message(attempt_id, "user", content)


def handle_proctor_preparation(
    server: AssessmentServer,
    attempt_id: int,
    user_response_type: Literal["Answer", "Ask for clarification"],
) -> str:
    """
    Increments counts and returns status message.
    System instructions and status messages are NOT persisted.
    """
    if user_response_type == "Answer":
        server.increment_stats(attempt_id, is_answer=True)
    elif user_response_type == "Ask for clarification":
        server.increment_stats(attempt_id, is_answer=False)
    else:
        raise ValueError(f"Unknown user response type {user_response_type}")

    status_message = server.get_status_message(attempt_id)
    return status_message


def handle_lm_student_response(
    server: AssessmentServer,
    attempt_id: int,
) -> Literal["Answer", "Ask for clarification"]:
    """
    Prompt LLM student to respond to question.
    """
    student_prompt = get_system_prompt("student", "question")
    chat = server.load_chat_for_llm(attempt_id, student_prompt, role="student")

    response: str = model(chat, StudentAnswer)  # type: ignore
    answer: StudentAnswer = StudentAnswer.model_validate_json(response)

    handle_student_message(server, attempt_id, answer.message)
    handle_proctor_preparation(server, attempt_id, answer.decision)

    return answer.decision


def handle_intro_chat() -> Chat:
    """
    Ephemeral intro chat for now.
    """
    prompt = get_system_prompt("proctor", "base")
    chat = Chat()
    chat.add_system_message(prompt)

    response: str = model(chat, Greeting)  # type: ignore
    greeting: Greeting = Greeting.model_validate_json(response)
    chat.add_assistant_message(greeting.message)

    return chat


def handle_question_grading(
    server: AssessmentServer,
    attempt_id: int,
) -> QuestionGrade:
    """
    Prompt the grader to evaluate the student's performance.
    """
    grade_prompt = get_system_prompt(role="grader", prompt_type="grade-question")
    chat = server.load_chat_for_llm(attempt_id, grade_prompt, role="grader")

    response: str = model(chat, QuestionGrade)  # type: ignore
    evaluation: QuestionGrade = QuestionGrade.model_validate_json(response)

    server.save_llm_result(attempt_id, evaluation.model_dump(), "question")
    return evaluation


def handle_proctor_response_decision(
    server: AssessmentServer, attempt_id: Optional[int] = None
) -> Response:
    """
    Prompt model to analyze student response and make a decision.
    """
    prompt = get_system_prompt("proctor", "decide-answer-response")
    chat = server.load_chat_for_llm(attempt_id, prompt, role="proctor")

    response = model(chat, Response)
    res_obj: Response = Response.model_validate_json(response)

    return res_obj


def handle_proctor_student_response(
    server: AssessmentServer, attempt_id: Optional[int], decision: Response
):
    """
    Prompt model to generate a conversational response based on decision.
    Yields chunks for streaming.
    """
    # 1. Prepare prompt
    prompt_template = get_system_prompt("proctor", "give-student-response")
    instruction = prompt_template.format(
        reasoning=decision.reasoning, decision=decision.decision
    )

    # 2. Load chat history with base proctor instructions
    # We use the instruction as the system prompt to guide the response
    chat = server.load_chat_for_llm(attempt_id, instruction, role="proctor")

    # 3. Stream from OpenAI
    stream = client.chat.completions.create(
        model=openai_model,
        messages=chat.messages,  # type: ignore
        stream=True,
    )

    full_response = ""
    for chunk in stream:
        content = chunk.choices[0].delta.content
        if content:
            full_response += content
            yield content


def handle_chapter_summary(
    server: AssessmentServer,
    chapter_attempt_id: int,
    chapter_title: str,
    questions: List[Question],
    attempts: List[QuestionAttempt],
) -> ChapterSummary:
    """
    Summarize chapter performance.
    """
    context = json.dumps(
        {
            "chapter_title": chapter_title,
            "questions": [q.question_text for q in questions],
            "evaluations": [a.grade_data for a in attempts if a.grade_data],
        },
        indent=2,
    )

    summary_prompt = get_system_prompt(role="grader", prompt_type="chapter-summary")
    chat = Chat()
    chat.add_system_message(summary_prompt)
    chat.add_user_message(f"Chapter data and evaluations:\n{context}")

    response = model(chat, ChapterSummary)
    summary: ChapterSummary = ChapterSummary.model_validate_json(response)

    server.save_llm_result(chapter_attempt_id, summary.model_dump(), "chapter")
    return summary


def handle_test_summary(
    server: AssessmentServer,
    assessment_id: int,
    chapter_summaries: List[ChapterSummary],
) -> TestSummary:
    """
    Summarize overall test performance.
    """
    context = json.dumps([s.model_dump() for s in chapter_summaries], indent=2)

    summary_prompt = get_system_prompt(role="grader", prompt_type="test-summary")
    chat = Chat()
    chat.add_system_message(summary_prompt)
    chat.add_user_message(f"Chapter summaries:\n{context}")

    response = model(chat, TestSummary)
    summary: TestSummary = TestSummary.model_validate_json(response)

    server.save_llm_result(assessment_id, summary.model_dump(), "test")
    return summary
