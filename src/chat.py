"""
Helper function for managing chat
"""

from openai import OpenAI
from dotenv import load_dotenv
import json
import outlines
from outlines.inputs import Chat
import os
from typing import Literal
import logging
from src.assessment_server import AssessmentServer
from src.models import (
    ChapterSummary,
    EvaluatorResponse,
    Greeting,
    QuestionGrade,
    Response,
    StudentAnswer,
    TestSummary,
)
from secret import get_secret

# configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# get OpenAI environment vars
# for API key, first try loading from .env
# if not present, try AWS secret
load_dotenv()
if "OPENAI_API_KEY" not in os.environ:
    os.environ["OPENAI_API_KEY"] = get_secret()


openai_model = os.environ.get("OPENAI_MODEL", "gpt-5.4")
client = OpenAI()
model = outlines.from_openai(client, openai_model)


"""
Prompt functions
"""

# RoleType refers to the various roles the LLM may assume in a conversation
# - Proctor: Role for giving test to student
# - Student: (In AI student mode) Role for answering Proctor model questions
# - Evaluator: Role for assessing Proctor's responses
# - Grader: Role for assinging a grade to each question's response
# Each of these four roles gets a unique chat history so that
# we can control what context they have access to
RoleType = Literal["proctor", "student", "evaluator", "grader"]

# ParticipantType refers to the main interlocutors of the chat
# This is used when updating multiple chats at once to decide
# what role the message should be given in each chat
ParticipantType = Literal["proctor", "student", "system"]

# Enumeration of all prompt types stored in prompts/ folder
PromptType = Literal[
    "initial",
    "question",
    "clarify",
    "answer",
    "grade-question",
    "chapter-summary",
    "test-summary",
]


def get_system_prompt(
    role: RoleType = "proctor",
    prompt_type: PromptType = "initial",
) -> str:

    system_prompt_path = f"./prompts/{role}/{prompt_type}-prompt.txt"
    with open(system_prompt_path) as f:
        system_prompt = f.read()
    return system_prompt


def update_all_chats(
    chat_dict: dict[str, Chat],
    role: Literal["proctor", "student", "assessment_server"],
    prompt: str,
) -> dict[str, Chat]:
    """
    Route message to all chats in the conversation. This message
    is used for Student/Proctor interactions and question data,
    since these messages are shared across chat histories.

    The only exception is assessment_server messages, which are
    not added to the Student chat history. This is because the
    'assessment_server' role is reserved for adding ALL question
    data, including answers and explanations. The question itself
    is served directly from the QuestionServer object but is put
    to the chats under the Proctor role.

    The logic for routing messages to chat histories is as follows:
    - system and question server messages always go to "system" role
    - main_chat: assistant is Proctor, user is Student
    - student_chat: assistant is Student, user is Proctor,
        assessment_server messages are excluded
    - evaluator: assistant is Proctor, user is Student
    - grader: assistant is Proctor, user is Student

    """
    main_chat = chat_dict["main_chat"]
    match role:
        case "assessment_server":
            main_chat.add_system_message(prompt)
        case "proctor":
            main_chat.add_assistant_message(prompt)
        case "student":
            main_chat.add_user_message(prompt)
        case _:
            raise ValueError("Unexpected role", role)

    chat_dict["main_chat"] = main_chat

    if "student_chat" in chat_dict:
        student_chat = chat_dict["student_chat"]
        match role:
            case "assessment_server":
                pass  # student does not get question data
            case "proctor":
                student_chat.add_user_message(prompt)
            case "student":
                student_chat.add_assistant_message(prompt)

        chat_dict["student_chat"] = student_chat

    if "evaluator_chat" in chat_dict:
        evaluator_chat = chat_dict["evaluator_chat"]
        match role:
            case "assessment_server":
                evaluator_chat.add_system_message(prompt)
            case "proctor":
                evaluator_chat.add_assistant_message(prompt)
            case "student":
                evaluator_chat.add_user_message(prompt)

        chat_dict["evaluator_chat"] = evaluator_chat

    if "grader_chat" in chat_dict:
        grader_chat = chat_dict["grader_chat"]
        match role:
            case "assessment_server":
                pass  # grader receives no shared system messages
            case "proctor":
                grader_chat.add_assistant_message(prompt)
            case "student":
                grader_chat.add_user_message(prompt)

        chat_dict["grader_chat"] = grader_chat

    return chat_dict


def add_system_message(
    chat_dict: dict[str, Chat],
    chat: Literal["main_chat", "student_chat", "evaluator_chat"],
    prompt: str,
) -> dict[str, Chat]:
    """
    Add system message to specified chat, where the Proctor model sees system messages
    in "main_chat", the Student model in "student_chat", and the Evaluator in "evaluator_chat"
    """
    match chat:
        case "main_chat":
            main_chat = chat_dict["main_chat"]
            main_chat.add_system_message(prompt)
            chat_dict["main_chat"] = main_chat
        case "student_chat":
            student_chat = chat_dict["student_chat"]
            student_chat.add_system_message(prompt)
            chat_dict["student_chat"] = student_chat
        case "evaluator_chat":
            evaluator_chat = chat_dict["evaluator_chat"]
            evaluator_chat.add_system_message(prompt)
            chat_dict["evaluator_chat"] = evaluator_chat
    return chat_dict


def handle_question(
    chat_dict: dict[str, Chat],
    assessment_server: AssessmentServer,
    do_advance: bool = True,
) -> dict[str, Chat]:
    """
    Writes question data to chat as system prompt and writes question text
    to chat interface for student to read. Return updated chat.
    """
    if do_advance:
        assessment_server.advance_question()
    question_data = assessment_server.get_current_question_data()
    question_json = json.dumps(question_data, indent=2)
    question_message = assessment_server.format_question(**question_data)

    # proctor and evaluator both see full question data (including answer)
    system_message = f"Current question data: {question_json}"
    chat_dict = add_system_message(chat_dict, chat="main_chat", prompt=system_message)
    if "evaluator_chat" in chat_dict:
        chat_dict = add_system_message(
            chat_dict, chat="evaluator_chat", prompt=system_message
        )
    print(system_message)

    # all chats get question message
    chat_dict = update_all_chats(chat_dict, role="proctor", prompt=question_message)

    return chat_dict


def handle_student_response(
    chat_dict: dict[str, Chat],
    user_response_type: Literal["Answer", "Ask for clarification"],
    assessment_server: AssessmentServer,
    prompt: str,
) -> dict[str, Chat]:
    """
    Adds user message to chat and then selects appropriate system prompt
    based on user response type.
    """
    chat_dict = update_all_chats(chat_dict, role="student", prompt=prompt)
    if user_response_type == "Answer":
        assessment_server.increment_attempts()
        system_prompt = get_system_prompt(role="proctor", prompt_type="answer")
    elif user_response_type == "Ask for clarification":
        assessment_server.increment_clarifications()
        system_prompt = get_system_prompt(role="proctor", prompt_type="clarify")
    else:
        raise ValueError(f"Unknown user response type {user_response_type}")

    status_message = assessment_server.get_attempt_and_clarification_message()
    chat_dict = update_all_chats(chat_dict, role="proctor", prompt=status_message)
    print(status_message)

    chat_dict = add_system_message(chat_dict, chat="main_chat", prompt=system_prompt)
    print(system_prompt)

    return chat_dict


def handle_lm_student_response(
    chat_dict: dict[str, Chat],
    assessment_server: AssessmentServer,
) -> tuple[dict[str, Chat], Literal["Answer", "Ask for clarification"]]:
    """
    Prompt LLM student to respond to question.
    Returns updated chat_dict and the student's decision type.
    """
    student_chat = chat_dict["student_chat"]

    # student system prompt only goes to student chat
    question_prompt = get_system_prompt("student", "question")
    chat_dict = add_system_message(
        chat_dict, chat="student_chat", prompt=question_prompt
    )

    # student response goes to all chats
    response = model(student_chat, StudentAnswer)
    answer: StudentAnswer = StudentAnswer.model_validate_json(response)
    chat_dict = handle_student_response(
        chat_dict, answer.decision, assessment_server, answer.message
    )

    return chat_dict, answer.decision


def handle_proctor_greeting(
    chat_dict: dict[str, Chat],
    assessment_server: AssessmentServer,
) -> dict[str, Chat]:
    """
    Adds initial system prompt to chat, generates assistant
    greeting and adds first question.
    """

    # proctor system prompt only goes to main chat
    system_prompt = get_system_prompt(role="proctor", prompt_type="initial")
    chat_dict = add_system_message(chat_dict, chat="main_chat", prompt=system_prompt)
    print(system_prompt)

    # evaluator initial prompt only goes to evaluator chat
    if "evaluator_chat" in chat_dict:
        evaluator_initial = get_system_prompt(role="evaluator", prompt_type="initial")
        chat_dict = add_system_message(
            chat_dict, chat="evaluator_chat", prompt=evaluator_initial
        )

    print("Getting greeting from assistant...")
    response = model(chat_dict["main_chat"], Greeting)
    greeting = Greeting.model_validate_json(response)
    chat_dict = update_all_chats(chat_dict, role="proctor", prompt=greeting.message)

    chat_dict = handle_question(chat_dict, assessment_server)
    return chat_dict


def handle_evaluator_response(
    chat_dict: dict[str, Chat],
    assessment_server: AssessmentServer,
    prompt_type: Literal["answer", "clarify"],
) -> tuple[dict[str, Chat], EvaluatorResponse]:
    """
    Prompt evaluator model to score the proctor's last response.
    The evaluator sees proctor as assistant and student as user,
    with its own system messages but none from main_chat or student_chat.
    """
    evaluator_prompt = get_system_prompt(role="evaluator", prompt_type=prompt_type)
    chat_dict = add_system_message(
        chat_dict, chat="evaluator_chat", prompt=evaluator_prompt
    )

    response_json = model(chat_dict["evaluator_chat"], EvaluatorResponse)
    evaluation = EvaluatorResponse.model_validate_json(response_json)
    print(f"Evaluator response: {response_json}")

    return chat_dict, evaluation


def handle_question_grading(
    chat_dict: dict[str, Chat],
    assessment_server: AssessmentServer,
) -> tuple[dict[str, Chat], QuestionGrade]:
    """
    Prompt the grader to evaluate the student's performance on the current question.
    Stores the evaluation in assessment_server and returns updated chat_dict and the eval.
    """
    grade_prompt = get_system_prompt(role="grader", prompt_type="grade-question")
    chat_dict = add_system_message(chat_dict, chat="grader_chat", prompt=grade_prompt)

    response_json = model(chat_dict["grader_chat"], QuestionGrade)
    evaluation = QuestionGrade.model_validate_json(response_json)
    assessment_server.add_question_grade(evaluation, assessment_server.chapter_index)
    print(f"Question eval: {response_json}")

    return chat_dict, evaluation


def handle_proctor_response(
    chat_dict: dict[str, Chat],
    assessment_server: AssessmentServer,
) -> tuple[Response, dict[str, Chat]]:
    """
    Prompt model to respond to last student message.
    Model will decide either to proceed to the next question
    or follow up on the current question. In the former case,
    print the next question and then return. In the latter,
    return immediately so that the student may respond.
    """

    # first get response to student's last message
    print("Getting assistant response to student input...")
    response_json = model(chat_dict["main_chat"], Response)
    response = Response.model_validate_json(response_json)

    # Full JSON response stored as system message and logged to console
    # Only "message" attribute revealed to user
    chat_dict = update_all_chats(chat_dict, role="proctor", prompt=response.message)
    system_message = f"Full assistant response in JSON format: {response_json}"
    chat_dict = add_system_message(chat_dict, chat="main_chat", prompt=system_message)

    # model decided to move on to next question
    if response.decision == "next_question":
        chat_dict, _ = handle_question_grading(chat_dict, assessment_server)
        chat_dict = handle_question(chat_dict, assessment_server)

    return response, chat_dict


def handle_chapter_summary(
    assessment_server: AssessmentServer,
    chapter_index: int,
) -> ChapterSummary:
    """
    Prompt the proctor to summarize a student's performance on a single chapter.
    Uses a fresh chat with the chapter's questions and evals as context.
    """
    chapter_data = assessment_server.get_chapter_data(chapter_index)
    evals = assessment_server.question_evals.get(chapter_index, [])

    context = json.dumps(
        {
            "chapter": chapter_index,
            "title": chapter_data["title"],
            "questions": chapter_data["questions"],
            "question_evaluations": [e.model_dump() for e in evals],
        },
        indent=2,
    )

    summary_prompt = get_system_prompt(role="grader", prompt_type="chapter-summary")
    chat = Chat()
    chat.add_system_message(summary_prompt)
    chat.add_user_message(f"Chapter data and evaluations:\n{context}")

    response_json = model(chat, ChapterSummary)
    summary = ChapterSummary.model_validate_json(response_json)
    print(f"Chapter {chapter_index} summary: {response_json}")
    return summary


def handle_test_summary(
    chapter_summaries: list[ChapterSummary],
) -> TestSummary:
    """
    Prompt the proctor to summarize overall student performance across all chapters.
    """
    context = json.dumps(
        [s.model_dump() for s in chapter_summaries],
        indent=2,
    )

    summary_prompt = get_system_prompt(role="grader", prompt_type="test-summary")
    chat = Chat()
    chat.add_system_message(summary_prompt)
    chat.add_user_message(f"Chapter summaries:\n{context}")

    response_json = model(chat, TestSummary)
    summary = TestSummary.model_validate_json(response_json)
    print(f"Test summary: {response_json}")
    return summary
