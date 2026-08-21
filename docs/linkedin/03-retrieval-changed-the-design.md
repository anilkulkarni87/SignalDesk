# Post 03 - Retrieval Changed the Design

SignalDesk's vector retriever reached 98% Recall@5.

The lexical baseline reached 68%.

The integrated product still serves lexical retrieval.

That apparent contradiction is one of the most useful lessons from the project.

The frozen 50-query benchmark measured:

```text
                 Recall@5   MRR      p95 query latency
lexical             68%     0.4697       5.129 ms
vector              98%     0.9007      40.470 ms
```

The vector result clearly improved retrieval quality on the curated benchmark.
But an experiment does not silently become a production dependency.

The later integrated workflow had bounded, known policy intents and accepted a
current-approved lexical index to keep the local serving architecture simple.
The vector evidence remains valid for broader semantic search, but adopting it
would also change cost, latency, deployment, and failure behavior.

This taught me to separate three decisions:

1. Which retriever wins an offline benchmark?
2. Which retriever fits the accepted serving workflow?
3. What new evidence would justify changing that serving decision?

RAG is a search problem before it is a generation problem. But search quality
is still only one part of the system decision.

The full scorecard, including failed targets and evidence boundaries:

https://anilkulkarni87.github.io/SignalDesk/experiments/

#RAG #VectorSearch #InformationRetrieval #AIEngineering

