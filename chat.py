"""
Helper function for managing chat
"""

from numpy import append
import streamlit as st
from openai import OpenAI
from dotenv import load_dotenv
from pydantic import BaseModel
import json
import outlines
from outlines.inputs import Chat
import os
from typing import Literal
import logging

from streamlit.delta_generator import Value

load_dotenv()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

openai_model = os.environ.get("OPENAI_MODEL", "gpt-4o")
client = OpenAI()
model = outlines.from_openai(client, openai_model)

"""
Question database management
"""

JSON_PATH = "./data/wildfire_questions_B.json"

ADVANCE_TYPE = Literal["next_question", "next_chapter", "end_test"]

QUESTION_TEMPLATE = """
## Concept: {concept_description}
**Type:** {question_format}
**Question:** {question_text}

You may ask {max_clarifications} clarification questions
and you have {max_answer_attempts} attempts to answer correctly
before the assessment will automatically progress to the next question.
"""


class QuestionServer:
    def __init__(self, json_path: str = JSON_PATH) -> None:
        self.json_path = json_path
        self.data = self.load_data()

        # chapter index corresponds to chapter number in course textbook
        # and so it is 1-indexed
        # question index corresponds to index in JSON array
        # and so it is 0-indexed, but starts at -1 since
        # 'handle_next_question' always increments question_index
        # at the beginning
        self.chapter_index = 1
        self.question_index = -1
        self.max_chapter = max(
            int(chapter_data["chapter"]) for chapter_data in self.data
        )

        # to prevent the student getting stuck on a single question,
        # we allow n=5 clarification questions and m=5 answer attempts,
        # then we automatically progress to the next question
        self.num_clarifications = 0
        self.num_answer_attempts = 0

        self.max_clarifications = 5
        self.max_answer_attempts = 5

    def load_data(self) -> list[dict[str, str | list[dict[str, str]]]]:
        with open(self.json_path) as f:
            data = json.load(f)
        return data

    def get_current_chapter_data(
        self,
    ) -> dict[str, str | list[dict[str, str]]]:
        chapter_data = [
            chapter
            for chapter in self.data
            if int(chapter["chapter"]) == self.chapter_index
        ]
        assert len(chapter_data) == 1
        return chapter_data[0]

    def increment_clarifications(self):
        self.num_clarifications = self.num_clarifications + 1

    def increment_attempts(self):
        self.num_answer_attempts = self.num_answer_attempts + 1

    def remaining_clarifications(self) -> int:
        return self.max_clarifications - self.num_clarifications

    def remaining_attempts(self) -> int:
        return self.max_answer_attempts - self.num_answer_attempts

    def get_attempt_and_clarification_message(self) -> str:
        remaining_attempts = self.remaining_attempts()
        remaining_clarifications = self.remaining_clarifications()
        if remaining_attempts <= 0:
            return "Max answer attempts reached for this question!"

        if remaining_clarifications <= 0:
            return f"Max clarification questions reached. {remaining_attempts} answer attempts remain."

        return f"There are {remaining_clarifications} clarification questions and {remaining_attempts} answer attempts remaining for this question."

    def get_question_status(
        self,
    ) -> Literal["attempts_and_clarifications", "no_clarifications", "no_attempts"]:
        if self.remaining_attempts() <= 0:
            return "no_attempts"
        if self.remaining_clarifications() <= 0:
            return "no_clarifications"
        return "attempts_and_clarifications"

    def get_current_question_data(self) -> dict[str, str]:
        chapter_data = self.get_current_chapter_data()
        question_data = chapter_data["questions"][self.question_index]
        assert type(question_data) is dict
        question_data = {
            "chapter": chapter_data["chapter"],
            "title": chapter_data["title"],
            **question_data,
        }
        return question_data

    def format_question(self, **question_data) -> str:
        question_str = QUESTION_TEMPLATE.format(
            max_clarifications=self.max_clarifications,
            max_answer_attempts=self.max_answer_attempts,
            **question_data,
        )
        return question_str

    def advance_question(self) -> ADVANCE_TYPE:
        """
        Advance to the next question within the chapter if available.
        If at the end of the chapter, advance to the next chapter instead,
        and if at end of last chapter, return 'end_test'.
        """

        self.num_answer_attempts = 0
        self.num_clarifications = 0

        question_index = self.question_index + 1

        chapter_data = self.get_current_chapter_data()
        chapter_num_questions = len(chapter_data["questions"])
        if question_index >= chapter_num_questions:
            # advance to next chapter and reset question index
            self.question_index = 0
            self.chapter_index += 1

            if self.chapter_index > self.max_chapter:
                return "end_test"
            return "next_question"

        self.question_index += 1
        return "next_question"


"""
Structured response types
"""


class Greeting(BaseModel):
    message: str


class Response(BaseModel):
    message: str
    reasoning: str
    decision: Literal["follow_up", "next_question"]


class StudentAnswer(BaseModel):
    message: str
    decision: Literal["Answer", "Ask for clarification"]


class EvaluatorResponse(BaseModel):
    fairness_score: int
    information_score: int
    explanation_score: int
    reasoning: str


"""
Prompt functions
"""


def get_system_prompt(
    role: Literal["assistant", "student", "evaluator"] = "assistant",
    prompt_type: Literal["initial", "question", "clarify", "answer"] = "initial",
) -> str:

    system_prompt_path = f"./prompts/{role}/{prompt_type}-prompt.txt"
    with open(system_prompt_path) as f:
        system_prompt = f.read()
    return system_prompt


def update_all_chats(
    chat_dict: dict[str, Chat],
    role: Literal["proctor", "student", "system"],
    prompt: str,
) -> dict[str, Chat]:
    """
    Add message to 'main_chat' (where assistant=proctor and user=student)
    and 'student_chat' (where assistant=student and user=proctor).
    """
    main_chat = chat_dict["main_chat"]
    match role:
        case "system":
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
            case "system":
                student_chat.add_system_message(prompt)
            case "proctor":
                student_chat.add_user_message(prompt)
            case "student":
                student_chat.add_assistant_message(prompt)

        chat_dict["student_chat"] = student_chat

    if "evaluator_chat" in chat_dict:
        evaluator_chat = chat_dict["evaluator_chat"]
        match role:
            case "system":
                pass  # evaluator receives no shared system messages
            case "proctor":
                evaluator_chat.add_assistant_message(prompt)
            case "student":
                evaluator_chat.add_user_message(prompt)

        chat_dict["evaluator_chat"] = evaluator_chat

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


def handle_next_question(
    chat_dict: dict[str, Chat], question_server: QuestionServer
) -> dict[str, Chat]:
    """
    Writes question data to chat as system prompt and writes question text
    to chat interface for student to read. Return updated chat.
    """
    question_server.advance_question()
    question_data = question_server.get_current_question_data()
    question_json = json.dumps(question_data, indent=2)
    question_message = question_server.format_question(**question_data)

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
    question_server: QuestionServer,
    prompt: str,
) -> dict[str, Chat]:
    """
    Adds user message to chat and then selects appropriate system prompt
    based on user response type.
    """
    chat_dict = update_all_chats(chat_dict, role="student", prompt=prompt)
    if user_response_type == "Answer":
        question_server.increment_attempts()
        system_prompt = get_system_prompt(role="proctor", prompt_type="answer")
    elif user_response_type == "Ask for clarification":
        question_server.increment_clarifications()
        system_prompt = get_system_prompt(role="proctor", prompt_type="clarify")
    else:
        raise ValueError(f"Unknown user response type {user_response_type}")

    status_message = question_server.get_attempt_and_clarification_message()
    chat_dict = update_all_chats(chat_dict, role="proctor", prompt=status_message)
    print(status_message)

    chat_dict = add_system_message(chat_dict, chat="main_chat", prompt=system_prompt)
    print(system_prompt)

    return chat_dict


def handle_lm_student_response(
    chat_dict: dict[str, Chat],
    question_server: QuestionServer,
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
        chat_dict, answer.decision, question_server, answer.message
    )

    return chat_dict, answer.decision


def handle_proctor_greeting(
    chat_dict: dict[str, Chat],
    question_server: QuestionServer,
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

    chat_dict = handle_next_question(chat_dict, question_server)
    return chat_dict


def handle_evaluator_response(
    chat_dict: dict[str, Chat],
    question_server: QuestionServer,
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


def handle_proctor_response(
    chat_dict: dict[str, Chat],
    question_server: QuestionServer,
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
        chat_dict = handle_next_question(chat_dict, question_server)

    return response, chat_dict
