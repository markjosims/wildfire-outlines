# Chat lifecycle migration

## Overview

The current chat lifecycle is overly complicated and, worse, has a leaky integration with the new SQL backend.
Rather than having a separate chat history for each role, have a single chat history for the student/proctor interaction and route system prompts based on role lazily.

## Conversation flow

A single conversation is scoped either to a particular question or to the greeting page.
All roles need to see, at a minimum, the interactions between proctor and student.
Each roles system prompt can be reliably determined by static question data and the type of conversational turn being requested.
Concretely for each role:

- **Proctor:**
  - For a question chat, proctor should see all question data, including answer key.
  - Responding to a student answer attempt: Route the prompt in @../prompts/proctor/answer-prompt.txt
  - Responding to a student request for clarification: Route the prompt in @../prompts/proctor/clarify-prompt.txt
  - For the greeting chat: Route the prompt in @../prompts/proctor/initial-prompt.txt

- **Grader:**
  - Conclusion of a question: Provide with question data including answer key, route prompt from @../prompts/grader/grade-question-prompt.txt
  - Chapter summary: Provide with all question data for chapter as well as the grade for each question, route prompt from ../prompts/grader/chapter-summary-prompt.txt
  - Test summary: Provide with all chapter summaries, route prompt from @../prompts/grader/test-summary-prompt.txt

- **Student:**
  - (Human) given question data but not answer key as well as chat history.
  - (LLM) same as human plus prompt from @../prompts/student/question-prompt.txt

## SQL interface

Each `chat` is linked to a `QuestionAttempt` object, and the greeting chat is linked to the `Assessment` table.

## Relevant functions and code

From @../src/chat.py:

- `update_all_chats()`
  - no longer need complex routing logic by role, also should not be used to get system prompts as those will now be passed lazily
  - also needs to update the SQL backend via the `DbManager` instance tied to the `AssessmentServer`
  - now needs to put `ChatMessage` object to SQL DB
- `add_system_message()`
  - likewise, complex routing logic by-role not needed, replace with a method to add system prompts for a single LLM API call
- `handle_*()`
  - replace `chat_dict` arg with `chat` (single `Chat`, not dict of `Chat` objects)

From @../app.py:

- Replace `chat_dict` with `chat`, also load `chat` from SQL db rather than streamlit session state.
- Otherwise, logic should be the same since `handle_*()` functions own prompting logic
