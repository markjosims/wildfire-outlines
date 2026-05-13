# Migration TODOs

## Phase 1: AssessmentServer Refactor
- [ ] Modify `AssessmentServer.__init__` to initialize `self.chats: dict[tuple[int, int], dict[str, Chat]]` (keyed by `(chapter, question_index)`).
- [ ] Add `self.active_question: tuple[int, int]` to track current view.
- [ ] Update `add_question_grade` to store grades indexed by `(chapter, question_index)`.
- [ ] Add `get_chat(chapter, q_idx)` and `set_chat(chapter, q_idx, chat_dict)` methods.
- [ ] Add `get_question_status_icon(chapter, q_idx)` to return the 3-way status (green/yellow/none).

## Phase 2: chat.py Refactor
- [ ] Update `handle_question` to retrieve/initialize the chat for the specific question.
- [ ] Ensure `update_all_chats` and other handlers work with the isolated `chat_dict` passed to them.
- [ ] Update `handle_proctor_response` to only advance if it's the current linear progression, otherwise just update the specific question's chat.

## Phase 3: app.py Frontend Rewrite
- [ ] Implement sidebar navigation for Chapters and Questions.
- [ ] Implement `render_question` to display the chat history for the *selected* question.
- [ ] Implement `render_greeting` for the initial state.
- [ ] Update main loop to react to sidebar selection.
- [ ] Implement Teacher Mode specific renders (`render_question_eval`, etc.).

## Phase 4: Summarization & Completion
- [ ] Implement `evaluate_remaining_questions` in `AssessmentServer`.
- [ ] Update the "End test early" / "Finish test" logic to use the new batch evaluation.
- [ ] Verify chapter and test summaries still work with the new data structure.
