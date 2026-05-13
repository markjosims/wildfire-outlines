from pydantic import BaseModel
from typing import Literal

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
    decision: Literal["follow_up", "next_question"]


class Greeting(BaseModel):
    message: str