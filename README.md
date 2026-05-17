# Wildfire Outlines

Codebase for LLM-guided assessment for Credit for Prior Learning (CPL) assessment for Firetek 207.
Frontend is implemented in Python with `streamlit`, backend is handled with `sqlite` with `sqlmodels` for Python bindings.

## Test flow

Assessment content is divided into 15 chapters with 5 questions per chapter, based on content in the Firetek 207 course textbook.
The student answers questions by conversing with the LLM proctor.
The LLM proctor probes the student to demonstrate understanding and reasoning, providing richer information for faculty evaluators than a traditional paper exam.
At test conclusion, the LLM is prompted to grade each question and give aggregate summaries for each chapter and for the assessment as a whole to help guide faculty evaluation.

Each student is assigned a unique exam code to enable anonymous saving of assessment progress.
This ensures persistence of data while guaranteeing data privacy.

## Frontend

Implemented in [app.py](./app.py).
Initial landing page prompts the student to generate an exam code if starting a new exam or input an existing code if resuming a session.
Once an exam session is loaded, the student may access the main assessment interface, where the student interacts with the proctor LLM.

The main interface consists of a greeting page where the student may ask the proctor for guidance on how to complete the exam and how to interact with the proctor, as well as a page for each question, where each question has a unique chat history.

Navigation is handled via the sidebar, allowing the user to browse questions by chapter and displaying which questions have not been attempted yet, which have been attempted, and which are completed.

## Backend

The backend database consists of a SQLite server with Python bindings provided by `sqlmodel`.
The database manages static assessment data (questions and answer keys) and dynamic data related to assessment session state, where each assessment state is tied to a student's unique exam code.
Database initialization and interfacing is handled by [db.py](./src/db.py).
Static assessment data is seeded by [migrate_questions.py](./scripts/migrate_questions.py), which reads the JSON data from [wildfire_questions_B.json](./data/wildfire_questions_B.json).
Database models are defined in [models.py](./src/models.py).

## LLM prompt routing

LLM prompting is handled by [chat.py](./src/chat.py).
This file handles response generation for various LLM 'roles' in the assessment, namely:

- **Proctor:** The main LLM the student interacts with, which probes the student to explain reasoning and provides clarification for terminology or question content.
- **Grader:** The LLM responsible for assessing student performance and generating evaluations to help guide faculty assessment of the exam.
- **Student:** An LLM prompted to answer the exam questions, also only relevant to contexts of validating the app.

See [prompts](./prompts/) for system prompts related to each role and more information on the conversation structure.

## Structured LLM responses

The `outlines` library handles structured LLM responses, e.g. outputting a grade for a question as an integer on a fixed scale.
Structured response models are defined in [models.py](./src/models.py).
