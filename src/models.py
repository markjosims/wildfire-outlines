"""
Contains models for structured LLM responses with `outlines`
and `sqlmodel` types for database management.
"""

from pydantic import BaseModel
from typing import Literal, List, Optional
from sqlmodel import SQLModel, Field, Relationship
from datetime import datetime, timezone

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


class EvaluatorResponse(BaseModel):
    fairness_score: int
    information_score: int
    explanation_score: int
    reasoning: str


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
    id: int = Field(primary_key=True)
    title: str
    questions: List["Question"] = Relationship(back_populates="chapter")


class Question(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    chapter_id: int = Field(foreign_key="chapter.id")
    concept_description: str
    difficulty: str
    question_text: str
    answer: str
    chapter: Chapter = Relationship(back_populates="questions")


class User(SQLModel, table=True):
    username: str = Field(primary_key=True)
    password_hash: str


class Assessment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(foreign_key="user.username")
    started_at: datetime = Field(default_factory=datetime.now(timezone.utc))
    attempts: List["QuestionAttempt"]

class QuestionAttempt(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    assessment_id: int = Field(foreign_key="assessment.id")
    question_id: int = Field(foreign_key="question.id")
    num_clarifications: int = Field(default=0)
    num_answer_attempts: int = Field(default=0)

    # Grade data
    answer_correct: Optional[bool] = None
    confidence: Optional[int] = None
    thoroughness: Optional[int] = None
    explanation: Optional[str] = None

    assessment: Assessment = Relationship(back_populates="attempts")
    chats: List["ChatHistory"] = Relationship(back_populates="attempt")

class ChatHistory(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    attempt_id: int = Field(foreign_key="questionattempt.id")
    role: Literal["student", "proctor", "evaluator", "system"]
    messages_json: str
    attempt: QuestionAttempt = Relationship(back_populates="chats")
