# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
streamlit run app.py
```

Requires an `.env` file with `OPENAI_API_KEY`. Optional env vars:

- `OPENAI_MODEL` — defaults to `gpt-4o`
- `ASSESSMENT_TYPE` — `human` (default) or `ai` (LLM plays the student)

## Installing Dependencies

```bash
pip install -r requirements.txt
```

## Data Pipeline

Questions are authored in Markdown (`data/wildfire_questions_A.md`, `data/wildfire_questions_B.md`) and converted to JSON via:

```bash
cd data && python ../scripts/jsonify_questions.py
```

The app loads from `data/wildfire_questions_B.json` by default (`JSON_PATH` in `chat.py`).

## Architecture

**Two-file structure:**

- `app.py` — Streamlit frontend. Manages `st.session_state` for `chat_dict` and `question_server`. Controls the human vs. AI assessment loop.
- `chat.py` — All LLM and question logic. Uses the `outlines` library wrapping OpenAI for structured JSON outputs.

**Dual-chat design:**
The system maintains two parallel `Chat` objects (from `outlines.inputs.Chat`):

- `main_chat` — the proctor's view: proctor is `assistant`, student is `user`
- `student_chat` — the student LLM's view (AI mode only): roles are flipped

`update_all_chats()` synchronizes messages across both chats with correct role assignments. System messages are sent selectively — full question JSON and proctor reasoning go only to `main_chat`; student instructions go only to `student_chat`.

**Question progression:**
`QuestionServer` tracks chapter/question indexes and attempt/clarification counts. The proctor's `Response` pydantic model includes a `decision` field (`follow_up` | `next_question`) that drives when to advance. Each question has a cap of 5 clarification questions and 5 answer attempts before auto-advancing.

**Prompt system:**
Prompts are loaded at runtime from `prompts/{role}/{type}-prompt.txt`. The proctor has four prompt types (`initial`, `question`, `answer`, `clarify`) injected as system messages depending on the student's last action (answer vs. clarification request).

**Structured outputs:**
Three pydantic models constrain LLM responses: `Greeting`, `Response` (proctor), and `StudentAnswer` (AI student). Only the `message` field of `Response` is shown to the student; `reasoning` and `decision` stay hidden as system messages.
