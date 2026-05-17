# Wildfire Outlines

LLM-guided assessment application for Credit for Prior Learning (CPL) for the FIRETEK 207 (Wildfire) course.

## Project Overview

The application facilitates a conversational assessment where students interact with an LLM "Proctor" to demonstrate their understanding of wildfire concepts. The proctor probes the student's reasoning, providing a richer assessment than traditional multiple-choice exams.

### Architecture

- **Frontend:** [Streamlit](https://streamlit.io/) provides the user interface.
- **Backend:** [SQLModel](https://sqlmodel.tiangolo.com/) (SQLAlchemy + Pydantic) with a **SQLite** database.
- **LLM Integration:** [Outlines](https://github.com/outlines-dev/outlines) for structured LLM responses and [OpenAI](https://openai.com/) as the primary provider.
- **State Management:** Stateless backend logic encapsulated in `AssessmentServer`.

## Getting Started

### Prerequisites

- Python 3.13+
- OpenAI API Key (set in `.env` or provided via `secret.py`)

### Installation

```bash
pip install -r requirements.txt
# OR
pip install -e .
```

### Database Setup

The database is initialized automatically on app startup. To seed the assessment questions:

```bash
python scripts/migrate_questions.py
```

### Running the Application

```bash
streamlit run app.py
```

## Project Structure

- `app.py`: Main Streamlit entry point. Handles routing, session state, and UI rendering.
- `src/`: Core application logic.
    - `assessment_server.py`: `AssessmentServer` class managing database operations, chat persistence, and assessment state.
    - `chat.py`: LLM interaction logic, prompt routing, and response generation.
    - `models.py`: Definitions for both SQLModel database tables and Pydantic structured response models.
- `prompts/`: Directory containing system prompts for different LLM roles (`proctor`, `grader`, `student`).
- `data/`: Static assessment content in JSON and Markdown formats.
- `scripts/`: Utility scripts for data migration and transformation.
- `plans/`: Documentation of architectural decisions and development plans.

## Development Conventions

### Data Models
All data models (both persistent and transient LLM structures) should be defined in `src/models.py`. We use `SQLModel` for database tables to leverage Pydantic's validation.

### LLM Roles
- **Proctor:** Interacts with the student, explains concepts, and probes for reasoning.
- **Grader:** Evaluates student responses, generates question grades, and summarizes chapter/test performance.
- **Student:** Used for automated testing and validation of the assessment flow.

### Prompt Management
System prompts are stored as `.txt` files in `prompts/{role}/`. Use `get_system_prompt` in `src/chat.py` to retrieve them.

### Database Interactions
Avoid direct database access in the frontend (`app.py`). Use the `AssessmentServer` methods for all persistence and state retrieval.

### Structured Responses
Use `outlines` for any LLM response that needs to follow a specific schema (e.g., grading, decision making). Define these schemas as Pydantic models in `src/models.py`.
