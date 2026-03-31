# Changes from original app

The new app is designed with simplicity and auditability in mind.
By constraining the LLMs outputs and offloading basic functions (printing and advancing questions) to Python code, we make the system more predictable while also reducing costs by shrinking the LLM's context window to only what is necessary.

| Original design | New design | Explanation |
| ------------- | -------------- | -------------- |
| LLM given all questions at once | Questions given one at a time | The prompt for the LLM said to progress through questions in a deterministic order. Rather than hoping the LLM will do this, it's simpler to have it hardcoded into the system. |
| LLM given question as prompt and LLM then writes question for student. | Questions printed directly to chat. | LLM provides interactivity when student engages with question, but there's no need for it to print the question itself. |
| LLM given single prompt at beginning to guide it. | Separate prompts are given 1. at beginning 2. when student asks for clarification and 3. when student gives an answer attempt | Model is constantly reminded of how to behave: stronger guardrails than a single prompt at onset. |
| LLM gives a single message responding to student and decides on its own whether to follow up, move to the next question, or end the test. | LLM must decide explicitly whether to advance to the next question or follow-up, give a reason for its decision AND give a message for the student. | More guardrails on model behavior. When model decides to advance, the next question is printed automatically without needing the LLM to do anything. |
| No adversarial evaluation. | Option for Student and Evaluator LLMs to interact with Proctor. | Adversarial evaluation (where on LLM evaluates another) gives a baseline we can use for rapidly exploring different features. We can also measure the correlation between LLM evaluation and human evaluation to audit reliability. |

- What thoughts do you have on the current system?
- What would you like explained better?
- What would you like to be added to it?
