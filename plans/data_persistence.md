# Data persistence

## Overview

At present, assessment state is stored purely in `streamlit` context. This means that if the connection is interrupted, the user loses all progress. We want to persist data for the user locally.

To achieve this, we will implement a lightweight, secure local authentication system using `argon2-cffi` for password hashing, and we will store both user credentials and serialized `AssessmentServer` state in a local SQLite database.

## Architecture

1. **Backend Storage:** A local SQLite database (`data/assessments.db`).
2. **Authentication:** `argon2-cffi` will securely hash passwords before they are stored in the database.
3. **State Serialization:** The `AssessmentServer` will be extended with `to_dict()` and `from_dict()` methods to serialize its state (attempts, chats, evaluations) into JSON strings, which will be saved in the SQLite database alongside the user record.
4. **Frontend Integration:** `app.py` will be updated to include a login/registration flow before showing the main assessment view.

---

## 1. Database Schema (SQLite)

We will use Python's built-in `sqlite3` module.

```sql
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    assessment_state TEXT -- JSON string containing the serialized AssessmentServer state
);
```

## 2. Authentication Flow (Argon2)

We need `argon2-cffi` installed (`pip install argon2-cffi`). We will create a new helper module, e.g., `src/db.py` to handle both the database interactions and the authentication.

**Key Operations:**

* **Register:** `ph.hash(password)` -> store `username` and `hash` in DB.
* **Login:** Fetch `hash` by `username`, verify with `ph.verify(hash, password)`.
* **Session:** Once logged in, store the `username` in `st.session_state`.

## 3. AssessmentServer Serialization

We need to convert the complex dictionary structures inside `AssessmentServer` into JSON-serializable dictionaries.

**Challenges:**

* Dictionary keys are currently tuples: `(chapter: int, q_idx: int)`. JSON requires string keys. We will convert them to a string format like `"chapter:q_idx"`.
* `chats` dictionary values are `dict[str, Chat]`. We need to extract the `messages` list from the `outlines.inputs.Chat` object.
* `question_evals` values are Pydantic `QuestionGrade` models. We need to use `.model_dump()`.

**Proposed Methods in `AssessmentServer` (`src/assessment_server.py`):**

```python
import json
from outlines.inputs import Chat
from src.models import QuestionGrade

class AssessmentServer:
    # ... existing methods ...

    def to_dict(self) -> dict:
        """Serializes dynamic state to a dictionary."""
        
        def serialize_keys(d: dict) -> dict:
            # Converts (int, int) keys to "int:int" strings
            return {f"{k[0]}:{k[1]}": v for k, v in d.items()}

        serialized_chats = {}
        for k, chat_dict in self.chats.items():
            key_str = f"{k[0]}:{k[1]}"
            serialized_chats[key_str] = {
                role: chat.messages for role, chat in chat_dict.items()
            }

        return {
            "num_clarifications": serialize_keys(self.num_clarifications),
            "num_answer_attempts": serialize_keys(self.num_answer_attempts),
            "question_evals": {
                f"{k[0]}:{k[1]}": v.model_dump() for k, v in self.question_evals.items()
            },
            "chats": serialized_chats
        }

    def from_dict(self, state: dict):
        """Restores state from a dictionary."""
        if not state:
            return

        def deserialize_keys(d: dict) -> dict:
            # Converts "int:int" strings back to (int, int) tuples
            result = {}
            for k_str, v in d.items():
                parts = k_str.split(":")
                result[(int(parts[0]), int(parts[1]))] = v
            return result

        self.num_clarifications = deserialize_keys(state.get("num_clarifications", {}))
        self.num_answer_attempts = deserialize_keys(state.get("num_answer_attempts", {}))
        
        # Restore QuestionGrades
        evals_dict = deserialize_keys(state.get("question_evals", {}))
        self.question_evals = {k: QuestionGrade(**v) for k, v in evals_dict.items()}

        # Restore Chats
        chats_dict = deserialize_keys(state.get("chats", {}))
        self.chats = {}
        for k, chat_roles_dict in chats_dict.items():
            self.chats[k] = {}
            for role, messages in chat_roles_dict.items():
                # Reconstruct the outlines Chat object
                chat_obj = Chat()
                chat_obj.messages = messages
                self.chats[k][role] = chat_obj
```

## 4. Database Manager (`src/db.py`)

A new module to handle SQLite connections, user auth, and state fetching/saving.

```python
import sqlite3
import json
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

DB_PATH = "data/assessments.db"
ph = PasswordHasher()

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                assessment_state TEXT
            )
        ''')

def register_user(username, password):
    hash_str = ph.hash(password)
    with sqlite3.connect(DB_PATH) as conn:
        try:
            conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", 
                         (username, hash_str))
            return True
        except sqlite3.IntegrityError:
            return False # Username exists

def verify_user(username, password):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
        row = cur.fetchone()
        if row:
            try:
                ph.verify(row[0], password)
                return True
            except VerifyMismatchError:
                pass
    return False

def save_assessment_state(username, state_dict):
    state_json = json.dumps(state_dict)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE users SET assessment_state = ? WHERE username = ?", 
                     (state_json, username))

def load_assessment_state(username):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT assessment_state FROM users WHERE username = ?", (username,))
        row = cur.fetchone()
        if row and row[0]:
            return json.loads(row[0])
    return None
```

## 5. Integration into `app.py`

Modify `app.py` to:

1. Initialize the database on startup.
2. Provide a login/registration UI if `st.session_state.username` is not set.
3. Once logged in, load the state into `AssessmentServer`.
4. Add save hooks when the assessment progresses.

**Changes required in `app.py`:**

```python
# ... imports ...
from src.db import init_db, register_user, verify_user, save_assessment_state, load_assessment_state

# Initialize DB
init_db()

# --- Auth Flow ---
if "username" not in st.session_state:
    st.subheader("Login or Register")
    tab1, tab2 = st.tabs(["Login", "Register"])
    
    with tab1:
        with st.form("login_form"):
            user = st.text_input("Username")
            pw = st.text_input("Password", type="password")
            if st.form_submit_button("Login"):
                if verify_user(user, pw):
                    st.session_state.username = user
                    st.rerun()
                else:
                    st.error("Invalid credentials")
                    
    with tab2:
        with st.form("register_form"):
            new_user = st.text_input("New Username")
            new_pw = st.text_input("New Password", type="password")
            if st.form_submit_button("Register"):
                if register_user(new_user, new_pw):
                    st.success("Registered! You can now login.")
                else:
                    st.error("Username already exists.")
                    
    st.stop() # Halt execution until logged in

# --- Server Initialization ---
def get_assessment_server():
    if "assessment_server" in st.session_state:
        return st.session_state.assessment_server
        
    assessment_server = AssessmentServer()
    
    # Load state from DB
    saved_state = load_assessment_state(st.session_state.username)
    if saved_state:
        assessment_server.from_dict(saved_state)
        
    st.session_state.assessment_server = assessment_server
    return assessment_server

# ... existing app logic ...

# --- Save Hook ---
# To ensure persistence, we need to save the state after any modification.
# A simple approach is to add a save call at the end of functions that mutate the state,
# or provide a wrapper/callback in `AssessmentServer` that triggers `save_assessment_state(st.session_state.username, self.to_dict())`.
```

## 6. Next Steps

1. Update `requirements.txt` with `argon2-cffi`.
2. Create `src/db.py` with the SQLite and Argon2 logic.
3. Modify `src/assessment_server.py` to include `to_dict` and `from_dict`.
4. Update `app.py` to require login, manage the `st.session_state.username`, and hook up the load functions.
5. Determine the exact points in `app.py` or `src/chat.py` to trigger `save_assessment_state`.
