# Post 02 - Structured LLM Evaluation

My first SignalDesk LLM experiment returned valid structured output on every
frozen case.

It still missed required evidence often enough to matter.

The 30-case result was:

```text
API success              100.0%
schema validity          100.0%
risk agreement            90.0%
required evidence         76.67%
```

One "accuracy" number would have hidden the actual weakness.

This changed how I thought about evaluating model-backed systems. Different
questions require different metrics:

- Did the API call complete?
- Can the application parse the response?
- Does the classification agree with the frozen label?
- Did the answer include the evidence required for that case?
- Did the model reference only features the application can resolve?
- What did the behavior cost in latency and tokens?

The deterministic/probabilistic boundary mattered too. SQL and typed tools kept
ownership of counts, rates, dates, and eligibility. The model selected and
interpreted relevant evidence; it did not become the calculator of record.

The lesson was not "structured output solves hallucination."

It was:

> Schema validity makes probabilistic output consumable. Behavioral evaluation
> makes changes reviewable.

The LLM engineering phase and frozen evidence are here:

https://anilkulkarni87.github.io/SignalDesk/journey/#llm-engineering

Next: why retrieving the right document still does not guarantee a grounded
answer.

#LLMEvaluation #AIEngineering #StructuredOutputs #DataEngineering

