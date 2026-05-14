# Prompts

This folder contains system prompts for the various roles in an assessment chat.
The roles are as follows:

- Proctor: Role for giving test to student
- Student: (In AI student mode) Role for answering Proctor model questions
- Evaluator: Role for assessing Proctor's responses
- Grader: Role for assinging a grade to each question's response

Each of these four roles gets a unique chat history so that we can control what context they have access to.

There are three types of conversational "participants": the student, the proctor, and the system.
The student/proctor distinction is necessary because it defines what messages are classified as user or assistant for each of the roles, i.e.:

- For the Proctor, Grader and Evaluator models: student=user, proctor=assistant
- For the Student model (in LLM-as-student mode): proctor=user, student=assistant

Each conversational stage is associated with a unique system prompt.
The prompt categories are as follows:

- initial: Initial system prompt given at start of every chat for the given Role
- question: Prompt given to each Role at the onset of a question chat
    (i.e. the question data itself as well as guidance for how to respond or
    handle a student response)
- clarify: Prompt given to proctor following a student request for clarification
    and to evaluator following the proctor's response
- answer: Prompt given to proctor following a student answer attempt and to evaluator
    following the proctor's response
- grade-question: Prompt given to grader after a question chat is concluded
- chapter-summary: Prompt given to grader to summarize all graded questions in a chapter
- test-summary: Prompt given to grader to summarize all graded chapters in an assessment