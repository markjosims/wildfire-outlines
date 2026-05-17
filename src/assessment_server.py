import random
import string
import json
from typing import Optional, List, Literal
from sqlmodel import Session, create_engine, select, and_, SQLModel
from outlines.inputs import Chat
from src.models import (
    Assessment,
    QuestionAttempt,
    ChatMessage,
    Question,
    Chapter,
    ChapterAttempt,
)

"""
Question database management
"""

QUESTION_TEMPLATE = """
## Concept: {concept_description}
**Type:** {question_format}
**Question:** {question_text}

You may ask {max_clarifications} clarification questions
and you have {max_answer_attempts} attempts to answer correctly
before the assessment will automatically progress to the next question.
"""


class AssessmentServer:
    def __init__(self, db_url: str = "sqlite:///data/wildfire.db"):
        self.engine = create_engine(db_url, connect_args={"check_same_thread": False})
        self.max_clarifications = 5
        self.max_answer_attempts = 5

    def init_db(self):
        """Initialize database tables."""
        SQLModel.metadata.create_all(self.engine)

    # --- Session Management ---

    def _generate_code(self) -> str:
        """Generate a unique exam code."""
        chars = string.ascii_uppercase + string.digits
        return "-".join(["".join(random.choices(chars, k=2)) for _ in range(3)])

    def create_assessment(self) -> tuple[int, str]:
        """Add a blank Assessment and return (id, code)."""
        with Session(self.engine) as session:
            code = self._generate_code()
            # Ensure uniqueness
            while session.exec(
                select(Assessment).where(Assessment.exam_code == code)
            ).first():
                code = self._generate_code()

            db_ass = Assessment(exam_code=code)
            session.add(db_ass)
            session.commit()
            session.refresh(db_ass)
            return db_ass.id, db_ass.exam_code

    def get_assessment_by_code(self, code: str) -> Optional[Assessment]:
        """Retrieve Assessment by code."""
        with Session(self.engine) as session:
            return session.exec(
                select(Assessment).where(Assessment.exam_code == code)
            ).first()

    # --- Question & Chapter Lookups ---

    def get_question(self, chapter_id: int, question_index: int) -> Optional[Question]:
        """Maps logical chapter ID and question index to DB Question object."""
        with Session(self.engine) as session:
            stmt = (
                select(Question)
                .where(Question.chapter_id == chapter_id)
                .order_by(Question.id)
            )
            questions = session.exec(stmt).all()
            return (
                questions[question_index] if question_index < len(questions) else None
            )

    def get_chapter_title(self, chapter_id: int) -> Optional[str]:
        with Session(self.engine) as session:
            chapter = session.get(Chapter, chapter_id)
            return chapter.title if chapter else None

    # --- Attempt Management ---

    def get_or_create_attempt(
        self, assessment_id: int, question_id: int
    ) -> QuestionAttempt:
        with Session(self.engine) as session:
            stmt = select(QuestionAttempt).where(
                and_(
                    QuestionAttempt.assessment_id == assessment_id,
                    QuestionAttempt.question_id == question_id,
                )
            )
            attempt = session.exec(stmt).first()
            if not attempt:
                attempt = QuestionAttempt(
                    assessment_id=assessment_id, question_id=question_id
                )
                session.add(attempt)
                session.commit()
                session.refresh(attempt)
            return attempt

    def increment_stats(self, attempt_id: int, is_answer: bool = True):
        """Increments attempt or clarification count in DB."""
        with Session(self.engine) as session:
            attempt = session.get(QuestionAttempt, attempt_id)
            if not attempt:
                return
            if is_answer:
                attempt.num_answer_attempts += 1
            else:
                attempt.num_clarifications += 1
            session.add(attempt)
            session.commit()

    # --- Chat Persistence (Lazy Reconstruction) ---

    def record_message(
        self,
        assessment_id: int,
        role: Literal["user", "assistant"],
        content: str,
        attempt_id: Optional[int] = None,
    ):
        """Saves a message to the unified chat log."""
        with Session(self.engine) as session:
            msg = ChatMessage(
                assessment_id=assessment_id,
                attempt_id=attempt_id,
                role=role,
                content=content,
            )
            session.add(msg)
            session.commit()

    def load_chat_for_llm(
        self,
        assessment_id: int,
        system_prompt: str,
        role: Literal["proctor", "student", "grader"],
        attempt_id: Optional[int] = None,
    ) -> Chat:
        """
        Lazily reconstructs a Chat object from DB messages.
        Injects question data dynamically based on the target role.
        """
        chat = Chat()
        chat.add_system_message(system_prompt)

        with Session(self.engine) as session:
            if attempt_id:
                attempt = session.get(QuestionAttempt, attempt_id)
                if not attempt:
                    return chat

                question = attempt.question

                # Inject question data
                q_data = {
                    "concept_description": question.concept_description,
                    "question_format": question.question_format,
                    "question_text": question.question_text,
                }
                if role in ["proctor", "grader"]:
                    q_data["answer_key"] = question.answer
                    q_data["explanation_ground_truth"] = question.explanation_text

                chat.add_system_message(
                    f"Current Question Context:\n{json.dumps(q_data, indent=2)}"
                )

                # Proctor also gets the formatted question text as a system message to know what was shown
                if role == "proctor":
                    chat.add_system_message(
                        f"The student was shown the following:\n{self.format_question(question)}"
                    )

                stmt = (
                    select(ChatMessage)
                    .where(ChatMessage.attempt_id == attempt_id)
                    .order_by(ChatMessage.timestamp, ChatMessage.id)
                )
            else:
                # Intro chat
                stmt = (
                    select(ChatMessage)
                    .where(
                        and_(
                            ChatMessage.assessment_id == assessment_id,
                            ChatMessage.attempt_id == None,
                        )
                    )
                    .order_by(ChatMessage.timestamp, ChatMessage.id)
                )

            messages = session.exec(stmt).all()

            for message in messages:
                if message.role == "user":
                    chat.add_user_message(message.content)
                elif message.role == "assistant":
                    chat.add_assistant_message(message.content)
            return chat

    # --- Grade & Summary Persistence ---

    def save_llm_result(
        self, target_id: int, result: dict, type: Literal["question", "chapter", "test"]
    ):
        """Saves JSON blob results (QuestionGrade, ChapterSummary, TestSummary)."""
        with Session(self.engine) as session:
            if type == "question":
                obj = session.get(QuestionAttempt, target_id)
                if obj:
                    obj.grade_data = result
            elif type == "chapter":
                obj = session.get(ChapterAttempt, target_id)
                if obj:
                    obj.summary_data = result
            elif type == "test":
                obj = session.get(Assessment, target_id)
                if obj:
                    obj.test_summary = result

            if obj:
                session.add(obj)
                session.commit()

    # --- UI Helpers ---

    def format_question(self, question: Question) -> str:
        return QUESTION_TEMPLATE.format(
            max_clarifications=self.max_clarifications,
            max_answer_attempts=self.max_answer_attempts,
            concept_description=question.concept_description,
            question_format=question.question_format,
            question_text=question.question_text,
        )

    def get_status_message(self, attempt_id: int) -> str:
        with Session(self.engine) as session:
            attempt = session.get(QuestionAttempt, attempt_id)
            if not attempt:
                return ""

            rem_attempts = self.max_answer_attempts - attempt.num_answer_attempts
            rem_clarifications = self.max_clarifications - attempt.num_clarifications

            if rem_attempts <= 0:
                return "Max answer attempts reached!"
            if rem_clarifications <= 0:
                return f"Max clarifications reached. {rem_attempts} answer attempts remain."
            return f"Remaining: {rem_clarifications} clarifications, {rem_attempts} answer attempts."

    def get_ungraded_attempts(self, assessment_id: int) -> List[QuestionAttempt]:
        """Returns all attempts that have messages but no grade_data."""
        with Session(self.engine) as session:
            stmt = (
                select(QuestionAttempt)
                .join(ChatMessage)
                .where(
                    and_(
                        QuestionAttempt.assessment_id == assessment_id,
                        QuestionAttempt.grade_data.is_(None),
                    )
                )
                .distinct()
            )
            return session.exec(stmt).all()

    def get_attempted_chapters(self, assessment_id: int) -> List[Chapter]:
        """Returns all chapters that have at least one question attempt."""
        with Session(self.engine) as session:
            stmt = (
                select(Chapter)
                .join(Question)
                .join(QuestionAttempt)
                .where(QuestionAttempt.assessment_id == assessment_id)
                .distinct()
                .order_by(Chapter.id)
            )
            return session.exec(stmt).all()

    def get_or_create_chapter_attempt(
        self, assessment_id: int, chapter_id: int
    ) -> ChapterAttempt:
        with Session(self.engine) as session:
            stmt = select(ChapterAttempt).where(
                and_(
                    ChapterAttempt.assessment_id == assessment_id,
                    ChapterAttempt.chapter_id == chapter_id,
                )
            )
            attempt = session.exec(stmt).first()
            if not attempt:
                attempt = ChapterAttempt(
                    assessment_id=assessment_id, chapter_id=chapter_id
                )
                session.add(attempt)
                session.commit()
                session.refresh(attempt)
            return attempt

    def get_question_status_icon(self, attempt: QuestionAttempt) -> str:
        """Returns colorless icon based on attempt state."""
        if attempt.grade_data:
            return "✔"
        if attempt.num_answer_attempts > 0:
            return "❔"
        return ""

    def get_next_incomplete_question(
        self, assessment_id: int, current_chapter_id: int, current_question_idx: int
    ) -> Optional[tuple[int, int]]:
        """
        Find the next question (chapter_id, question_idx) in sequence that has not been graded.
        """
        with Session(self.engine) as session:
            chapters = session.exec(select(Chapter).order_by(Chapter.id)).all()

            found_current = False
            for chapter in chapters:
                for idx, question in enumerate(chapter.questions):
                    if not found_current:
                        if (
                            chapter.id == current_chapter_id
                            and idx == current_question_idx
                        ):
                            found_current = True
                        continue

                    attempt = self.get_or_create_attempt(assessment_id, question.id)
                    if not attempt.grade_data:
                        return (chapter.id, idx)

            return None

    def check_all_complete(self, assessment_id: int) -> bool:
        """
        Checks if all questions in the database have a graded attempt for this assessment.
        """
        with Session(self.engine) as session:
            # Get total number of questions
            total_questions = session.exec(select(Question)).all()
            total_count = len(total_questions)

            # Get count of graded attempts for this assessment
            stmt = select(QuestionAttempt).where(
                and_(
                    QuestionAttempt.assessment_id == assessment_id,
                    QuestionAttempt.grade_data.is_not(None),
                )
            )
            graded_attempts = session.exec(stmt).all()
            graded_count = len(graded_attempts)

            return graded_count >= total_count
