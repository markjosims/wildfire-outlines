# Comprehensive Data Persistence: Unified Assessment Server

## Overview

We move to a centralized **SQLite** database managed by a unified `AssessmentServer`. This class absorbs all `DBManager` responsibilities, acting as the single source of truth for both static question data and dynamic session state.

All structured LLM outputs (Grades and Summaries) are stored consistently as **JSON blobs** in the database to ensure schema flexibility and simplified code.

---

## 1. Database Schema (`src/models.py`)

We use `SQLModel` with `JSON` columns for all LLM-generated structured data.

### Suggested Code for `src/models.py`

```python
from typing import Optional, List, Literal
from datetime import datetime, timezone
from sqlmodel import SQLModel, Field, Relationship, Column, JSON

class Chapter(SQLModel, table=True):
    id: int = Field(primary_key=True)
    title: str
    questions: List["Question"] = Relationship(back_populates="chapter")
    attempts: List["ChapterAttempt"] = Relationship(back_populates="chapter")

class Question(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    chapter_id: int = Field(foreign_key="chapter.id")
    concept_description: str
    difficulty: str
    question_text: str
    answer: str
    explanation_text: str # Required ground truth
    
    chapter: Chapter = Relationship(back_populates="questions")
    attempts: List["QuestionAttempt"] = Relationship(back_populates="question")

class Assessment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    exam_code: str = Field(index=True, unique=True)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Store TestSummary as JSON
    test_summary: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    
    attempts: List["QuestionAttempt"] = Relationship(back_populates="assessment")
    chapter_attempts: List["ChapterAttempt"] = Relationship(back_populates="assessment")

class ChapterAttempt(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    assessment_id: int = Field(foreign_key="assessment.id")
    chapter_id: int = Field(foreign_key="chapter.id")
    
    # Store ChapterSummary as JSON
    summary_data: Optional[dict] = Field(default=None, sa_column=Column(JSON))

    assessment: Assessment = Relationship(back_populates="chapter_attempts")
    chapter: Chapter = Relationship(back_populates="attempts")

class QuestionAttempt(SQLModel, table=True):
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

class ChatMessage(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    attempt_id: int = Field(foreign_key="questionattempt.id")
    role: Literal["student", "proctor", "system"]
    content: str
    attempt: QuestionAttempt = Relationship(back_populates="chats")
```

---

## 2. Implementation Strategy

1. **Uniform Storage**: All LLM results use `model_dump()` to save and `model_validate()` to load.
2. **Server Simplification**: `AssessmentServer` provides a single `save_llm_result(target_id, model_instance)` method.
3. **Chat Reconstruction**: `AssessmentServer.load_chat_for_llm` rebuilds `Chat` objects on demand from `ChatMessage` log.
