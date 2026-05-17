# Migration Plan: Unified Assessment Server (Detailed)

## 1. Goal

Consolidate `DbManager` (`src/db.py`) and `AssessmentServer` (`src/assessment_server.py`) into a single, stateless class. Remove all in-memory dictionaries and legacy JSON loading from the server.

---

## 2. Legacy Code References

### `src/assessment_server.py` (To be Refactored)

- **Stateful Dicts (REMOVE)**: `self.num_clarifications`, `self.num_answer_attempts`, `self.chats`, `self.question_evals`.
- **JSON Data (REMOVE)**: `self.data = self.load_data()` (Questions now in DB).
- **Logic (KEEP/ADAPT)**: `format_question`, `get_attempt_and_clarification_message`.

### `src/db.py` (To be Deleted)

- **CRUD (MOVE)**: `create_assessment`, `get_or_create_attempt`, `save_chat_message`, `save_grade`.

---

## 3. New Unified API (`src/assessment_server.py`)

### A. Core Initialization

```python
class AssessmentServer:
    def __init__(self, db_url: str = "sqlite:///data/wildfire.db"):
        self.engine = create_engine(db_url, connect_args={"check_same_thread": False})
        self.max_clarifications = 5
        self.max_answer_attempts = 5
```

### B. Session & Identity

| Action | Legacy Signature | New Signature |
|---|---|---|
| Create Exam | `DbManager.create_assessment()` | `create_assessment(self) -> tuple[int, str]` |
| Resume Exam | `DbManager.get_assessment_by_code(code)` | `get_assessment_by_code(self, code: str) -> Optional[Assessment]` |

### C. Question & Attempt Logic

The server now queries the `Question` table instead of `self.data` list.

```python
def get_question(self, chapter_id: int, question_index: int) -> Optional[Question]:
    """
    Replaces get_question_data(). 
    Query: select(Question).where(Question.chapter_id == chapter_id).order_by(Question.id)
    """

def get_or_create_attempt(self, assessment_id: int, question_id: int) -> QuestionAttempt:
    """Moved from DbManager. Base for all question state."""
```

### D. Chat Persistence (The "Lazy" System)

We replace the complex `chat_dict` (which duplicated messages across proctor/student/evaluator objects) with a single message log.

| Purpose | Legacy | New Unified Signature |
|---|---|---|
| **Save** | `update_all_chats(...)` | `record_message(self, attempt_id: int, role: str, content: str)` |
| **Load** | `get_chat(...)` | `load_chat_for_llm(self, attempt_id: int, system_prompt: str) -> Chat` |

**Reconstruction Logic**:

```python
def load_chat_for_llm(self, attempt_id: int, system_prompt: str) -> Chat:
    # 1. Fetch QuestionAttempt (with relationship 'chats')
    # 2. Sort chats by timestamp, id
    # 3. Create fresh outlines.inputs.Chat()
    # 4. Add system_prompt
    # 5. Loop msgs: if role == 'student' -> add_user, else if 'proctor' -> add_assistant, else -> add_system
    # 6. Return Chat object
```

### E. Result Persistence (JSON Blobs)

Consolidated method for all structured LLM outputs.

```python
def save_llm_result(self, target_id: int, result: dict, type: Literal["question", "chapter", "test"]):
    """
    Replaces add_question_grade and DbManager.save_grade.
    Saves to: QuestionAttempt.grade_data, ChapterAttempt.summary_data, or Assessment.test_summary.
    """
```

---

## 4. Integration Context for `src/chat.py`

`chat.py` must be updated to stop managing `chat_dict`.

**Example Change (Proctor Response)**:

- **Old**: `handle_proctor_response(chat_dict, assessment_server, ...)`
- **New**:

  ```python
  def handle_proctor_response(server: AssessmentServer, attempt_id: int):
      # 1. Load context
      prompt = get_system_prompt("proctor", "initial")
      chat = server.load_chat_for_llm(attempt_id, prompt)
      # 2. Call LLM
      resp = model(chat, Response)
      # 3. Persist
      server.record_message(attempt_id, "proctor", resp.message)
      return resp
  ```

---

## 5. Migration Checklist

1. [ ] **Models**: Confirm `src/models.py` uses `grade_data`, `summary_data`, and `test_summary` as `Column(JSON)`.
2. [ ] **Server**: Implement the `AssessmentServer` class as described in Section 3.
3. [ ] **Cleanup**: Delete `src/db.py`.
4. [ ] **Chat**: Update all `handle_*` functions in `src/chat.py` to use `AssessmentServer` + `attempt_id`.
5. [ ] **App**: Update `app.py` to initialize `st.session_state.server = AssessmentServer()`.
