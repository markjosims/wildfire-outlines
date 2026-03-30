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

    def load_data(self) -> list[dict[str, str | dict[str, str]]]:
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
        question_data: dict[str, str] = chapter_data["questions"][self.question_index]
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


"""
Prompt functions
"""


def get_system_prompt(
    role: Literal["assistant", "student"] = "assistant",
    prompt_type: Literal["initial", "question", "clarify", "answer"] = "initial",
) -> str:

    system_prompt_path = f"./prompts/{role}/{prompt_type}-prompt.txt"
    with open(system_prompt_path) as f:
        system_prompt = f.read()
    return system_prompt


def handle_next_question(chat: Chat, question_server: QuestionServer) -> Chat:
    """
    Writes question data to chat as system prompt and writes question text
    to chat interface for student to read. Return updated chat.
    """
    question_server.advance_question()
    question_data = question_server.get_current_question_data()
    question_json = json.dumps(question_data, indent=2)
    question_message = question_server.format_question(**question_data)

    system_message = f"Current question data: {question_json}"
    chat.add_system_message(system_message)
    print(system_message)
    chat.add_assistant_message(question_message)

    return chat


def handle_student_response(
    chat: Chat,
    user_response_type: Literal["Answer", "Ask for clarification"],
    question_server: QuestionServer,
    prompt: str,
) -> Chat:
    """
    Adds user message to chat and then selects appropriate system prompt
    based on user response type.
    """
    chat.add_user_message(prompt)
    if user_response_type == "Answer":
        question_server.increment_attempts()
        system_prompt = get_system_prompt(role="assistant", prompt_type="answer")
    elif user_response_type == "Ask for clarification":
        question_server.increment_clarifications()
        system_prompt = get_system_prompt(role="assistant", prompt_type="clarify")
    else:
        raise ValueError(f"Unknown user response type {user_response_type}")

    status_message = question_server.get_attempt_and_clarification_message()
    chat.add_assistant_message(status_message)
    print(status_message)

    chat.add_system_message(system_prompt)
    print(system_prompt)
    return chat


def handle_assistant_greeting(
    chat: Chat,
    question_server: QuestionServer,
) -> Chat:
    """
    Adds initial system prompt to chat, generates assistant
    greeting and adds first question.
    """
    system_prompt = get_system_prompt(role="assistant", prompt_type="initial")
    chat.add_system_message(system_prompt)
    print(system_prompt)

    print("Getting greeting from assistant...")
    response = model(chat, Greeting)
    greeting = Greeting.model_validate_json(response)
    chat.add_assistant_message(greeting.message)

    chat = handle_next_question(chat, question_server)
    return chat


def handle_assistant_response(
    chat: Chat,
    question_server: QuestionServer,
) -> Chat:
    """
    Prompt model to respond to last student message.
    Model will decide either to proceed to the next question
    or follow up on the current question. In the former case,
    print the next question and then return. In the latter,
    return immediately so that the student may respond.
    """

    # first get response to student's last message
    print("Getting assitant response to student input...")
    response_json = model(chat, Response)
    response = Response.model_validate_json(response_json)

    # Full JSON response stored as system message and logged to console
    # Only "message" attribute revealed to user
    chat.add_assistant_message(response.message)
    system_message = f"Full assistant response in JSON format: {response_json}"
    chat.add_system_message(system_message)

    # model decided to move on to next question
    if response.decision == "next_question":
        chat = handle_next_question(chat, question_server)

    return chat
