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


class QuestionServer:
    def __init__(self, json_path: str = JSON_PATH) -> None:
        self.json_path = json_path
        self.data = self.load_data()

        # chapter index corresponds to chapter number in course textbook
        # and so it is 1-indexed
        # question index corresponds to index in JSON array
        # and so it is 0-indexed
        self.chapter_index = 1
        self.question_index = 0
        self.max_chapter = max(
            int(chapter_data["chapter"]) for chapter_data in self.data
        )

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

    def get_current_question(self) -> dict[str, str]:
        chapter_data = self.get_current_chapter_data()
        question_data: dict[str, str] = chapter_data["questions"][self.question_index]
        question_data = {
            "chapter": chapter_data["chapter"],
            "title": chapter_data["title"],
            **question_data,
        }
        return question_data

    def advance_question(self) -> ADVANCE_TYPE:
        """
        Advance to the next question within the chapter if available.
        If at the end of the chapter, advance to the next chapter instead,
        and if at end of last chapter, return 'end_test'.
        """
        question_index = self.question_index + 1

        chapter_data = self.get_current_chapter_data()
        chapter_num_questions = len(chapter["questions"])
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


class Response(BaseModel):
    content: str
    comment: str
    decision: Literal["follow_up", "next_question"]


class Question(BaseModel):
    content: str
    comment: str


"""
Prompt functions
"""


def get_system_prompt(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    system_prompt_path = "./system-prompt.txt"
    with open(system_prompt_path) as f:
        system_prompt = f.read()
    messages.append(
        {
            "role": "system",
            "content": system_prompt,
        }
    )
    return messages


def get_model_response(
    messages: list[dict[str, str]],
    question_server: QuestionServer,
    write_funct=print,
) -> list[dict[str, str]]:
    # first get response to student's last message
    response_json = model(Chat(messages), Response)
    response = Response.model_validate_json(response_json)
    print(response.model_dump_json(indent=2))

    write_funct(response.content)
    messages.append(
        {"role": "system", "content": f"Assistant responded with {response.decision}"}
    )
    messages.append({"role": "assistant", "content": response.content})

    # then have model output next question, if applicable
    if response.decision == "next_question":
        question_server.advance_question()
        question = question_server.get_current_question()
        question_str = json.dumps(question)
        messages.append({"role": "system", "content": f"Next question: {question_str}"})

        question_json: Question = model(Chat(messages), Question)
        question_object = Question.model_validate_json(question_json)
        content = write_funct(question_object.content)
        print(question_object.model_dump_json(indent=2))
        messages.append({"role": "assistant", "content": content})
        messages.append(
            {
                "role": "system",
                "content": f"Assistant commentary: {model_question.comment}",
            }
        )

    return messages
