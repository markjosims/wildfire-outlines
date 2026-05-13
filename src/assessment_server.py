import json
from typing import Literal
from src.models import QuestionGrade

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


class AssessmentServer:
    def __init__(self, json_path: str = JSON_PATH) -> None:
        self.json_path = json_path
        self.data = self.load_data()

        # chapter index corresponds to chapter number in course textbook
        # and so it is 1-indexed
        # question index corresponds to index in JSON array
        # and so it is 0-indexed, but starts at None so
        # 'handle_next_question' can set it to 0
        # on first call
        self.chapter_index = 1
        self.question_index = None
        self.max_chapter = max(
            int(chapter_data["chapter"]) for chapter_data in self.data
        )

        # active_question tracks what is currently displayed in the UI
        # (chapter, question_index)
        self.active_question: Optional[tuple[int, int]] = None

        # to prevent the student getting stuck on a single question,
        # we allow n=5 clarification questions and m=5 answer attempts,
        # then we automatically progress to the next question
        self.num_clarifications = 0
        self.num_answer_attempts = 0

        self.max_clarifications = 5
        self.max_answer_attempts = 5

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
        return max(chapters) if chapters else self.chapter_index

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

        if self.question_index is None:
            question_index = 0
        else:
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

        self.question_index = question_index
        return "next_question"

    def skip_to_question(self, chapter_index: int, question_index: int) -> None:
        self.chapter_index = chapter_index
        self.question_index = question_index
        self.num_answer_attempts = 0
        self.num_clarifications = 0