# Post 01 - The Journey Starts Before the Model

I built an AI agent only after spending three milestones making sure I knew what
problem it was supposed to solve.

SignalDesk is an 18-milestone learning project built around one fictional
customer-intelligence workflow.

The journey starts with questions that are easy to skip:

- Who performs the investigation?
- What decision are they trying to make?
- Where does the current workflow lose time or quality?
- What should improve?
- What must not become worse?
- Which authority must remain with a person?

Only then did I build the synthetic customer data, Customer 360 layer, LLM
evaluation harness, retrieval system, tools, agent workflow, approval boundary,
analyst interface, observability, and failure tests.

That ordering became the most important lesson of the project:

```text
workflow before technology
metric before model
authority before automation
```

SignalDesk does not use real customer data, and it does not claim measured
business impact. Its value is showing how each engineering decision can be tied
to evidence and an explicit limitation.

I have published the complete journey as six phases and 18 chapters:

https://anilkulkarni87.github.io/SignalDesk/

The next post covers the first difficult transition: moving from deterministic
SQL to probabilistic model behavior without giving up software discipline.

#AIEngineering #DataEngineering #FDE #LLMOps

