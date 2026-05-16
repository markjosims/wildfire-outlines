# Comprehensive Data Persistence: Anonymous Exam Codes

## Overview
We will move to a centralized **SQLite** database managed by **SQLModel**. This provides concurrency safety for multiple simultaneous users and persistent session recovery via **Anonymous Exam Codes**.

---

## 1. Database Schema (`src/models.py`)
We revert to `SQLModel` to gain DB-native relationships while keeping Pydantic validation.

```python
from typing import Optional, List, Dict
from datetime import datetime, timezone
from sqlmodel import SQLModel, Field, Relationship

class Chapter(SQLModel, table=True):
    id: int = Field(primary_key=True)
    title: str
    questions: List["Question"] = Relationship(back_populates="chapter")

class Question(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    chapter_id: int = Field(foreign_key="chapter.id")
    concept_description: str
    difficulty: Optional[str] = None
    question_text: str
    answer: str
    explanation_text: str
    
    chapter: Chapter = Relationship(back_populates="questions")
    attempts: List["QuestionAttempt"] = Relationship(back_populates="question")

class Assessment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    exam_code: str = Field(index=True, unique=True)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    attempts: List["QuestionAttempt"] = Relationship(back_populates="assessment")

class QuestionAttempt(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    assessment_id: int = Field(foreign_key="assessment.id")
    question_id: int = Field(foreign_key="question.id")
    
    num_clarifications: int = 0
    num_answer_attempts: int = 0

    # Grade data
    answer_correct: Optional[bool] = None
    confidence: Optional[int] = None
    thoroughness: Optional[int] = None
    explanation: Optional[str] = None

    assessment: Assessment = Relationship(back_populates="attempts")
    question: Question = Relationship(back_populates="attempts")
    chats: List["ChatHistory"] = Relationship(back_populates="attempt")

class ChatHistory(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    attempt_id: int = Field(foreign_key="questionattempt.id")
    role: str # student, proctor, evaluator, system
    content: str # Raw message text
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    attempt: QuestionAttempt = Relationship(back_populates="chats")
```

---

## 2. Database Manager (`src/db.py`)
The `DBManager` handles all low-level SQL operations.

```python
import random
import string
from typing import Optional, List
from sqlmodel import Session, create_engine, select, and_
from .models import Assessment, QuestionAttempt, ChatHistory, Question, SQLModel

DB_URL = "sqlite:///data/wildfire.db"
engine = create_engine(DB_URL, connect_args={"check_same_thread": False})

class DBManager:
    def init_db(self):
        SQLModel.metadata.create_all(engine)

    def generate_code(self) -> str:
        chars = string.ascii_uppercase + string.digits
        return '-'.join([''.join(random.choices(chars, k=2)) for _ in range(3)])

    def create_assessment(self) -> str:
        with Session(engine) as session:
            code = self.generate_code()
            while session.exec(select(Assessment).where(Assessment.exam_code == code)).first():
                code = self.generate_code()
            db_ass = Assessment(exam_code=code)
            session.add(db_ass)
            session.commit()
            return code

    def get_assessment_by_code(self, code: str) -> Optional[Assessment]:
        with Session(engine) as session:
            return session.exec(select(Assessment).where(Assessment.exam_code == code)).first()

    def get_or_create_attempt(self, assessment_id: int, question_id: int) -> QuestionAttempt:
        with Session(engine) as session:
            stmt = select(QuestionAttempt).where(
                and_(QuestionAttempt.assessment_id == assessment_id, 
                     QuestionAttempt.question_id == question_id)
            )
            attempt = session.exec(stmt).first()
            if not attempt:
                attempt = QuestionAttempt(assessment_id=assessment_id, question_id=question_id)
                session.add(attempt)
                session.commit()
                session.refresh(attempt)
            return attempt

    def save_chat_message(self, attempt_id: int, role: str, content: str):
        with Session(engine) as session:
            msg = ChatHistory(attempt_id=attempt_id, role=role, content=content)
            session.add(msg)
            session.commit()

    def update_attempt_stats(self, attempt_id: int, clarifications: int, attempts: int):
        with Session(engine) as session:
            db_att = session.get(QuestionAttempt, attempt_id)
            db_att.num_clarifications = clarifications
            db_att.num_answer_attempts = attempts
            session.add(db_att)
            session.commit()

    def save_grade(self, attempt_id: int, grade_data: dict):
        with Session(engine) as session:
            db_att = session.get(QuestionAttempt, attempt_id)
            for k, v in grade_data.items():
                setattr(db_att, k, v)
            session.add(db_att)
            session.commit()
```

---

## 3. AssessmentServer Refactor (`src/assessment_server.py`)
The server acts as the controller, mapping logical indices (chapter, q_idx) to DB IDs.

### Key Changes:
- **`__init__`**: Accepts `db: DBManager` and `assessment_id: int`.
- **`get_chat`**: Loads `ChatHistory` from DB and reconstructs `outlines.inputs.Chat`.
- **`set_chat`**: Only saves the *latest* message to `ChatHistory` table.
- **`question_evals`**: Replaced by `db.save_grade`.

```python
class AssessmentServer:
    def __init__(self, db: DBManager, assessment_id: int):
        self.db = db
        self.assessment_id = assessment_id
        # Cache question mapping for index -> ID lookups
        self._id_map = self._build_id_map() 

    def _get_q_id(self, ch: int, qi: int) -> int:
        return self._id_map[(ch, qi)]

    def get_chat(self, ch: int, qi: int) -> Optional[Dict[str, Chat]]:
        q_id = self._get_q_id(ch, qi)
        attempt = self.db.get_or_create_attempt(self.assessment_id, q_id)
        if not attempt.chats: return None
        
        # In this simple version, we assume all messages in ChatHistory 
        # belong to the 'main_chat'.
        messages = [{"role": c.role, "content": c.content} for c in attempt.chats]
        return {"main_chat": Chat(messages=messages)}

    def save_message(self, ch: int, qi: int, role: str, content: str):
        q_id = self._get_q_id(ch, qi)
        attempt = self.db.get_or_create_attempt(self.assessment_id, q_id)
        self.db.save_chat_message(attempt.id, role, content)
```

---

## 4. Frontend Integration (`app.py`)
A "Gatekeeper" checks for `st.session_state.exam_code` before rendering.

```python
db = DBManager()
db.init_db()

if "exam_code" not in st.session_state:
    # --- Landing Page ---
    st.title("Wildfire Assessment")
    input_code = st.text_input("Resume Session (Code):").upper()
    if st.button("Resume"):
        ass = db.get_assessment_by_code(input_code)
        if ass:
            st.session_state.exam_code = ass.exam_code
            st.session_state.assessment_id = ass.id
            st.rerun()
        else: st.error("Code not found.")
        
    if st.button("New Assessment"):
        code = db.create_assessment()
        ass = db.get_assessment_by_code(code)
        st.session_state.exam_code = code
        st.session_state.assessment_id = ass.id
        st.rerun()
else:
    # --- Main App ---
    if "assessment_server" not in st.session_state:
        st.session_state.assessment_server = AssessmentServer(
            db=db, 
            assessment_id=st.session_state.assessment_id
        )
    # ... rest of app ...
```

---

## 5. Next Steps
1. **Revert `src/models.py`** to SQLModel.
2. **Implement `src/db.py`** with the CRUD methods.
3. **Migrate questions** to DB using `scripts/migrate_questions.py`.
4. **Update `AssessmentServer`** and `app.py`.
