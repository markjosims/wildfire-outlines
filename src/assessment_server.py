import json
from typing import Literal, Optional
from src.models import QuestionGrade

"""
Question database management
"""

JSON_PATH = "./data/wildfire_questions_B.json"

QUESTION_TEMPLATE = """
## Concept: {concept_description}
**Type:** {question_format}
**Question:** {question_text}

You may ask {max_clarifications} clarification questions
and you have {max_answer_attempts} attempts to answer correctly
before the assessment will automatically progress to the next question.
"""


class AssessmentServer:
    def __init__(self, json_path: str = JSON_PATH) -> None:
        self.json_path = json_path
        self.data = self.load_data()

        self.max_chapter = max(
            int(chapter_data["chapter"]) for chapter_data in self.data
        )

        self.max_clarifications = 5
        self.max_answer_attempts = 5

        # attempts: dict[(chapter, q_idx), int]
        self.num_clarifications: dict[tuple[int, int], int] = {}
        self.num_answer_attempts: dict[tuple[int, int], int] = {}

        # chats: dict[(chapter, q_idx), chat_dict]
        self.chats: dict[tuple[int, int], dict[str, "Chat"]] = {}
        # question_evals: dict[(chapter, q_idx), QuestionGrade]
        self.question_evals: dict[tuple[int, int], QuestionGrade] = {}

    def get_chat(self, chapter: int, q_idx: int) -> Optional[dict[str, "Chat"]]:
        return self.chats.get((chapter, q_idx))

    def set_chat(self, chapter: int, q_idx: int, chat_dict: dict[str, "Chat"]) -> None:
        self.chats[(chapter, q_idx)] = chat_dict

    def add_question_grade(
        self, eval: "QuestionGrade", chapter: int, q_idx: int
    ) -> None:
        self.question_evals[(chapter, q_idx)] = eval

    def get_question_status_icon(self, chapter: int, q_idx: int) -> str:
        """
        Return icon based on proctor's judgment:
        - ✅ if satisfied (correct and thorough)
        - ❓ if follow-up needed
        - "" if unanswered
        """
        eval = self.question_evals.get((chapter, q_idx))
        if not eval:
            return ""

        if eval.answer_correct and eval.thoroughness >= 4:
            return "✅"
        return "❓"

    def get_chapter_data(
        self, chapter_index: int
    ) -> dict[str, str | list[dict[str, str]]]:
        chapter_data = [
            chapter for chapter in self.data if int(chapter["chapter"]) == chapter_index
        ]
        assert len(chapter_data) == 1
        return chapter_data[0]

    def attempted_chapters(self) -> list[int]:
        return sorted(list(set(k[0] for k in self.question_evals.keys())))

    def last_chapter_attempted(self) -> int:
        chapters = self.attempted_chapters()
        return max(chapters) if chapters else 1

    def evaluate_remaining_questions(self, grade_callback) -> None:
        """
        Iterate through all questions that have chat history but no grade.
        Call grade_callback(chat_dict, chapter, q_idx) for each.
        """
        for (chapter, q_idx), chat_dict in self.chats.items():
            if (chapter, q_idx) not in self.question_evals:
                # only grade if student has spoken
                if len(chat_dict["main_chat"].messages) > 3: # greeting + question + status > 3
                     grade_callback(chat_dict, chapter, q_idx)

    def load_data(self) -> list[dict[str, str | list[dict[str, str]]]]:
        with open(self.json_path) as f:
            data = json.load(f)
        return data

    def increment_clarifications(self, chapter: int, q_idx: int):
        key = (chapter, q_idx)
        self.num_clarifications[key] = self.num_clarifications.get(key, 0) + 1

    def increment_attempts(self, chapter: int, q_idx: int):
        key = (chapter, q_idx)
        self.num_answer_attempts[key] = self.num_answer_attempts.get(key, 0) + 1

    def remaining_clarifications(self, chapter: int, q_idx: int) -> int:
        return self.max_clarifications - self.num_clarifications.get((chapter, q_idx), 0)

    def remaining_attempts(self, chapter: int, q_idx: int) -> int:
        return self.max_answer_attempts - self.num_answer_attempts.get((chapter, q_idx), 0)

    def get_attempt_and_clarification_message(self, chapter: int, q_idx: int) -> str:
        rem_attempts = self.remaining_attempts(chapter, q_idx)
        rem_clarifications = self.remaining_clarifications(chapter, q_idx)
        if rem_attempts <= 0:
            return "Max answer attempts reached for this question!"

        if rem_clarifications <= 0:
            return f"Max clarification questions reached. {rem_attempts} answer attempts remain."

        return f"There are {rem_clarifications} clarification questions and {rem_attempts} answer attempts remaining for this question."

    def get_question_status(
        self, chapter: int, q_idx: int
    ) -> Literal["attempts_and_clarifications", "no_clarifications", "no_attempts"]:
        if self.remaining_attempts(chapter, q_idx) <= 0:
            return "no_attempts"
        if self.remaining_clarifications(chapter, q_idx) <= 0:
            return "no_clarifications"
        return "attempts_and_clarifications"

    def get_question_data(self, chapter_index: int, question_index: int) -> dict[str, str]:
        chapter_data = self.get_chapter_data(chapter_index)
        question_data = chapter_data["questions"][question_index]
        assert type(question_data) is dict
        question_data = {
            "chapter": str(chapter_index),
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
