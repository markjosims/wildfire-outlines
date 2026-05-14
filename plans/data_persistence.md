# Data persistence

## Overview

At present, assessment state is stored purely in `streamlit` context, and questions are loaded from JSON files. This makes progress fragile and data management cumbersome. We will move all data—questions, user accounts, and assessment progress—into a local SQLite database (`data/wildfire.db`) using a relational schema managed by `SQLModel`.

## Architecture

1.  **SQLite Database:** Centralized storage for all entities.
2.  **SQLModel ORM:** We use `SQLModel` (built on Pydantic and SQLAlchemy) for type-safe, relational data management.
3.  **Authentication:** `argon2-cffi` for secure password hashing.
4.  **Migration Script:** A new script `scripts/migrate_questions.py` will import existing JSON questions into the database using SQLModel sessions.

---

## 1. Database Schema (`src/models.py`)

We will define our tables as `SQLModel` classes. This allows us to use them both as database tables and as Pydantic models for validation.

```python
from typing import Optional, List
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship

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
    started_at: datetime = Field(default_factory=datetime.utcnow)
    attempts: List["QuestionAttempt"] = Relationship(back_populates="assessment")

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
    chats: List["Chat"] = Relationship(back_populates="attempt")

class ChatHistory(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    attempt_id: int = Field(foreign_key="questionattempt.id")
    role: str # 'student', 'proctor', etc.
    messages_json: str # Serialized list of messages
    attempt: QuestionAttempt = Relationship(back_populates="chats")
```

---

## 2. Migration Script (`scripts/migrate_questions.py`)

```python
import json
import glob
from sqlmodel import Session, create_engine, select
from src.models import Chapter, Question, SQLModel

DB_URL = "sqlite:///data/wildfire.db"
engine = create_engine(DB_URL)

def migrate():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        for json_file in glob.glob("data/*.json"):
            with open(json_file, 'r') as f:
                data = json.load(f)
                for chapter_data in data:
                    chap_id = int(chapter_data['chapter'])
                    chapter = Chapter(id=chap_id, title=chapter_data['title'])
                    session.merge(chapter) # Upsert chapter
                    
                    for q_data in chapter_data['questions']:
                        # Check if question exists by text to avoid dupes
                        statement = select(Question).where(Question.question_text == q_data['question_text'])
                        if not session.exec(statement).first():
                            q = Question(chapter_id=chap_id, **q_data)
                            session.add(q)
        session.commit()
```

---

## 3. Database Manager (`src/db.py`)

```python
from sqlmodel import Session, create_engine, select
from src.models import User, Assessment, QuestionAttempt, Chat, SQLModel
from argon2 import PasswordHasher

ph = PasswordHasher()
DB_URL = "sqlite:///data/wildfire.db"
engine = create_engine(DB_URL)

class DBManager:
    def init_db(self):
        SQLModel.metadata.create_all(engine)

    def register_user(self, username, password):
        with Session(engine) as session:
            if session.get(User, username): return False
            user = User(username=username, password_hash=ph.hash(password))
            session.add(user)
            session.commit()
            return True

    def get_or_create_assessment(self, username):
        with Session(engine) as session:
            statement = select(Assessment).where(Assessment.username == username).order_by(Assessment.started_at.desc())
            assessment = session.exec(statement).first()
            if assessment: return assessment.id
            
            assessment = Assessment(username=username)
            session.add(assessment)
            session.commit()
            return assessment.id

    def update_attempt(self, assessment_id, question_id, **kwargs):
        with Session(engine) as session:
            statement = select(QuestionAttempt).where(
                QuestionAttempt.assessment_id == assessment_id,
                QuestionAttempt.question_id == question_id
            )
            attempt = session.exec(statement).first()
            if not attempt:
                attempt = QuestionAttempt(assessment_id=assessment_id, question_id=question_id)
            
            for k, v in kwargs.items():
                setattr(attempt, k, v)
            
            session.add(attempt)
            session.commit()
            return attempt.id

    def save_chat(self, attempt_id, role, messages):
        import json
        with Session(engine) as session:
            statement = select(Chat).where(Chat.attempt_id == attempt_id, Chat.role == role)
            chat = session.exec(statement).first()
            if not chat:
                chat = Chat(attempt_id=attempt_id, role=role)
            
            chat.messages_json = json.dumps(messages)
            session.add(chat)
            session.commit()
```

---

## 4. AssessmentServer Integration

`AssessmentServer` will use `DBManager` for persistence.

```python
class AssessmentServer:
    def __init__(self, db_manager, assessment_id):
        self.db = db_manager
        self.assessment_id = assessment_id
        # ... load state from DB ...

    def save_chat_to_db(self, chapter, q_idx, role, messages):
        q_id = self.get_q_id(chapter, q_idx)
        attempt_id = self.db.update_attempt(self.assessment_id, q_id)
        self.db.save_chat(attempt_id, role, messages)
```

---

## 5. Next Steps

1.  **Add `sqlmodel` and `argon2-cffi`** to `requirements.txt`.
2.  **Implement `scripts/migrate_questions.py`** to seed `wildfire.db`.
3.  **Update `src/models.py`** with SQLModel classes.
4.  **Create `src/db.py`** with `DBManager`.
5.  **Refactor `src/assessment_server.py` and `app.py`**.
