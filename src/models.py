"""
Contains models for structured LLM responses with `outlines`
and `sqlmodel` types for database management.
"""

from pydantic import BaseModel
from typing import Literal, List, Optional
from sqlmodel import SQLModel, Field, Relationship, Column, JSON
from datetime import datetime, timezone
from enum import Enum
from sqlalchemy.orm import clear_mappers

# Streamlit stability: Clear mappers and metadata before re-defining models
clear_mappers()
SQLModel.metadata.clear()

"""
Structured response types
"""


class TestSummary(BaseModel):
    overall_score: Literal[1, 2, 3, 4, 5]
    summary: str
    strengths: list[str]
    areas_for_improvement: list[str]


class ChapterSummary(BaseModel):
    chapter: int
    overall_score: Literal[1, 2, 3, 4, 5]
    summary: str
    strengths: list[str]
    weaknesses: list[str]


class QuestionGrade(BaseModel):
    answer_correct: bool
    confidence: Literal[1, 2, 3, 4, 5]
    thoroughness: Literal[1, 2, 3, 4, 5]
    explanation: str


class StudentAnswer(BaseModel):
    message: str
    decision: Literal["Answer", "Ask for clarification"]


class Response(BaseModel):
    message: str
    reasoning: str
    decision: Literal["follow_up", "question_complete"]


class Greeting(BaseModel):
    message: str


"""
Database types
"""


class Chapter(SQLModel, table=True):
    """
    Static data for a chapter in the assessment.
    """

    __table_args__ = {"extend_existing": True}
    id: int = Field(primary_key=True)
    title: str
    questions: List["Question"] = Relationship(back_populates="chapter")
    attempts: List["ChapterAttempt"] = Relationship(back_populates="chapter")


class Question(SQLModel, table=True):
    """
    Static data for a question in the assessment.
    """

    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    chapter_id: int = Field(foreign_key="chapter.id")
    concept_description: str
    question_text: str
    question_format: str
    answer: str
    explanation_text: str  # Required ground truth

    chapter: Chapter = Relationship(back_populates="questions")
    attempts: List["QuestionAttempt"] = Relationship(back_populates="question")


class Assessment(SQLModel, table=True):
    """
    State for an assessment session.
    """

    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    exam_code: str = Field(index=True, unique=True)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Store TestSummary as JSON
    test_summary: Optional[dict] = Field(default=None, sa_column=Column(JSON))

    attempts: List["QuestionAttempt"] = Relationship(back_populates="assessment")
    chapter_attempts: List["ChapterAttempt"] = Relationship(back_populates="assessment")
    chats: List["ChatMessage"] = Relationship(back_populates="assessment")


class ChapterAttempt(SQLModel, table=True):
    """
    State tracking summary for a given chapter in an assessment.
    """

    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    assessment_id: int = Field(foreign_key="assessment.id")
    chapter_id: int = Field(foreign_key="chapter.id")

    # Store ChapterSummary as JSON
    summary_data: Optional[dict] = Field(default=None, sa_column=Column(JSON))

    assessment: Assessment = Relationship(back_populates="chapter_attempts")
    chapter: Chapter = Relationship(back_populates="attempts")


class QuestionAttempt(SQLModel, table=True):
    """
    State for conversation and answer attempts for a given question.
    """

    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    assessment_id: int = Field(foreign_key="assessment.id")
    question_id: int = Field(foreign_key="question.id")
    num_clarifications: int = Field(default=0)
    num_answer_attempts: int = Field(default=0)

    # Store QuestionGrade as JSON
    grade_data: Optional[dict] = Field(default=None, sa_column=Column(JSON))

    assessment: Assessment = Relationship(back_populates="attempts")
    question: Question = Relationship(back_populates="attempts")
    chats: List["ChatMessage"] = Relationship(back_populates="attempt")


class ChatRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class ChatMessage(SQLModel, table=True):
    """
    A single persisted user-visible message.

    Greeting messages are tied directly to `Assessment`.
    Question messages are tied to `QuestionAttempt`.
    """

    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    assessment_id: Optional[int] = Field(default=None, foreign_key="assessment.id")
    attempt_id: Optional[int] = Field(default=None, foreign_key="questionattempt.id")
    role: ChatRole
    content: str
    assessment: Optional["Assessment"] = Relationship(back_populates="chats")
    attempt: Optional["QuestionAttempt"] = Relationship(back_populates="chats")
