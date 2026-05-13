# Migration TODOs

## Phase 1: AssessmentServer Refactor (DONE)
- [x] Modify `AssessmentServer.__init__` to initialize `self.chats: dict[tuple[int, int], dict[str, Chat]]` (keyed by `(chapter, question_index)`).
- [x] Update `add_question_grade` to store grades indexed by `(chapter, question_index)`.
- [x] Add `get_chat(chapter, q_idx)` and `set_chat(chapter, q_idx, chat_dict)` methods.
- [x] Add `get_question_status_icon(chapter, q_idx)` to return the 3-way status (green/yellow/none).
- [x] Remove all "next_question" and "advance" logic from the server.
- [x] Make attempt and clarification tracking per-question.

## Phase 2: chat.py Refactor (DONE)
- [x] Update `handle_question` to retrieve/initialize the chat for the specific question.
- [x] Ensure `update_all_chats` and other handlers work with the isolated `chat_dict` passed to them.
- [x] Remove all "advance" and "next_question" logic from `handle_proctor_response` and other handlers.
- [x] Accept `chapter` and `q_idx` in all handlers.
- [x] Rename `next_question` decision to `question_complete`.

## Phase 3: app.py Frontend Rewrite (DONE)
- [x] Implement sidebar navigation for Chapters and Questions.
- [x] Implement `render_greeting` for the initial state.
- [x] Implement `render_question` to display the chat history for the *selected* question.
- [x] Implement `render_question_eval` (For teacher mode).
- [x] Update main loop to react to sidebar selection.
- [x] Implement "Next Question" button in the UI that updates the selected indices.
- [x] Implement Teacher Mode specific renders (`render_evaluator_feedback`, etc.).

## Phase 4: Summarization & Completion (DONE)
- [x] Implement `evaluate_remaining_questions` in `AssessmentServer`.
- [x] Update the "End test early" / "Finish test" logic to use the new batch evaluation.
- [x] Verify chapter and test summaries still work with the new data structure.

## Phase 5: Global Greeting & Question Lifecycle (DONE)
- [x] Refactor `handle_proctor_greeting` in `chat.py` to `handle_intro_chat` (one-shot global greeting, no `handle_question` call).
- [x] Modify `app.py` to call and display the global greeting during the "Intro" phase.
- [x] Update `render_question` in `app.py` to initialize chats with system prompts and question text, but skip the proctor greeting model call.
- [x] Ensure `handle_question` remains a pure data injection function.

## Phase 6: Eager UI Updates (DONE)
- [x] Split `handle_student_response` in `chat.py` into `handle_student_message` and `handle_proctor_preparation`.
- [x] Update `app.py` to render student and status messages eagerly before triggering the proctor response spinner.
