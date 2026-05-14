# Assessment migration

## Overview

The current app delivers the test by iterating through the questions in the JSON database successively.
At every new question, the proctor is prompted with the entire chat history.
This has several disadvantages:

- **Context length:** The context length for the conversation increases monotonically across the assessment.
    This means that response times will get longer quadratically as the assessment progresses.
- **Unintuitive for users:** The monotonic context length affects humans too.
    Students are familiar with traditional paper tests that allow them to flip pages to view different questions, and revisit questions they find difficult.

This should be migrated to a new pattern where a single question is displayed at a time, with an interface on the sidebar allowing the user to navigate across chapters and questions.
Each question in the navigation menu should have a three-way indicator icon describing its status: green checkmark if the student has answered and the AI Proctor is satisfied with the answers thoroughness, a yellow question mark if the student has answered but the AI Proctor judges follow-up is needed, and no icon if the quetion is unanswered.

This has the following advantages:

- Shorter context for LLM and intuitive structure for users.
- Clear segregation of data: rather than one long chat history, each question gets its own history.

## Test loop

### Test loop: current implementation

The `AssessmentServer` class will need major rewriting.
Rather than simply serving question data, it should be the new hub for question data, student responses, and evaluator judgments.

The snippets in @src/app.py related to printing messages will need to be modified so that they only print the chat context for the activate question:

```python
# print all non-system messages to chat
for message in st.session_state.chat_dict["main_chat"].messages:
    if message["role"] == "system":
        continue
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

```

Likewise the output of all of the `handle` functions will need to be tracked the active question rather than appending to a global `chat_dict` object.

### Test loop: Changes to make

By file:

- The `AssessmentServer` class in @src/assessment_server.py will include a chat dict containing student, proctor and evaluator messages alongside the question text.
- The `handle_*` functions in @src/chat.py can mostly be left as-is.

- Add `render_*` helpers to @src/app.py, viz
  - `render_greeting`: Render assessment greeting before any question has been activated
  - `render_question`: Render chat history for a particular question
  - `render_question_eval`: (For teacher mode) render the LLM's eval on the student's answer for a given question
  - `render_evaluator_feedback`: (For teacher mode) render the evaluator LLM's feedback on the proctor LLM's response to the student
  - the sidebar in `app.py` should support buttons for selecting chapter and question

## Student feedback

### Student feedback: Current implementation

Uses `handle_chapter_summary` to evaluate each chapter, and then uses `handle_test_summary` to summarize the entire test.

```python
with st.spinner("Generating results..."):
    qs: AssessmentServer = st.session_state.assessment_server
    chapter_summaries: list[ChapterSummary] = []
    for ch in qs.attempted_chapters():
        chapter_summaries.append(handle_chapter_summary(qs, ch))
    test_summary: TestSummary = handle_test_summary(chapter_summaries)
    st.session_state.chapter_summaries = chapter_summaries
    st.session_state.test_summary = test_summary
```

Question evaluations are stored in the `AssessmentServer` object

```python
def add_question_grade(self, eval: "QuestionGrade", chapter: int) -> None:
    if chapter not in self.question_evals:
        self.question_evals[chapter] = []
    self.question_evals[chapter].append(eval)
```

Each evaluation is passed by the `handle_question_grading` function.

```python
def handle_question_grading(
    chat_dict: dict[str, Chat],
    assessment_server: AssessmentServer,
) -> tuple[dict[str, Chat], QuestionGrade]:
    """
    Prompt the grader to evaluate the student's performance on the current question.
    Stores the evaluation in assessment_server and returns updated chat_dict and the eval.
    """
    grade_prompt = get_system_prompt(role="grader", prompt_type="grade-question")
    chat_dict = add_system_message(chat_dict, chat="grader_chat", prompt=grade_prompt)

    response_json = model(chat_dict["grader_chat"], QuestionGrade)
    evaluation = QuestionGrade.model_validate_json(response_json)
    assessment_server.add_question_grade(evaluation, assessment_server.chapter_index)
    print(f"Question eval: {response_json}")

    return chat_dict, evaluation
```

### Student feedback: Changes to make

On test conclusion, generate a proctor evaluation for every question that has a student response but no proctor evaluation.
Modify the following files:

- @src/assessment_server.py: add function `evaluate_remaining_questions` that allows a callback function when each question is graded
- @app.py: add function `render_eval`
  - passes callback to `evaluate_remaining_questions` that renders a message indicating the current question being evaluated
  - for each chapter generate chapter summary with `handle_chapter_summary` rendering a message to the user for each chapter
  - then render a message before summarizing the entire test with `handle_test_summary`
