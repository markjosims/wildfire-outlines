# Two stage response

## Overview

Rather than have the LLM give a decision **and** student feedback in one response, split these into two messages.
The first message prompts the LLM to give the decision, then the second has them output a user-facing response.

## Current implementation context

The function `handle_proctor_response` gets a structured response with the `Response` model

```python
class Response(BaseModel):
    message: str
    reasoning: str
    decision: Literal["follow_up", "question_complete"]
```

```python
# first get response to student's last message
print("Getting assistant response to student input...")
response_json = model(chat_dict["main_chat"], Response)
response = Response.model_validate_json(response_json)
```

## Files to modify

- @prompts/proctor/answer-prompt.txt: split into two new files "decide-answer-response.txt" and "give-student-response.txt" reflecting stage.
- @src/models.py: remove "message" attribute from `Response` model
- @src/chat.py: split function `handle_proctor_response` into two new functions: `handle_proctor_response_decision` and `handle_proctor_student_response`
  - `handle_proctor_response_decision` prompts with "decide-answer-response.txt", llm output `Response` model
  - `handle_proctor_student_response` prompts with "give-student-response.txt", llm output text stream
- @app.py: modify function `render_question` to display a spinner while `handle_proctor_response_decision` is being generated and stream message from `handle_proctor_student_response`