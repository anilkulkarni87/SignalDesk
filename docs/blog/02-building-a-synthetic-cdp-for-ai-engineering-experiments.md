# Building a Synthetic CDP for AI Engineering Experiments

After defining the SignalDesk problem and workflows, the next step was to build the data foundation underneath it.

My first instinct could have been simple: use Faker, generate thousands of customers, orders, and events, and move on.

But that would have created fake data without proving that the data actually represented the customer situations SignalDesk needs to investigate.

So I started treating synthetic data as an engineering problem of its own.

## Fake rows are not enough

SignalDesk eventually needs to investigate questions such as:

> Why has this customer's engagement declined?

That means the data needs to contain more than customers and orders. It needs behavior that changes over time, support problems, campaign interactions, identity-resolution issues, subscriptions, and consent.

The synthetic CDP eventually grew to 12 domains, including customers, identities, sessions, events, orders, support tickets, campaign exposures, subscriptions, and consent preferences.

I also deliberately added the kind of messiness that exists in real customer data:

- anonymous activity that is resolved later,
- duplicate events,
- late-arriving events,
- null profile fields,
- refunded orders,
- unresolved support tickets,
- different customer timezones.

The goal was not perfect data. The goal was controlled imperfection.

## The first big lesson came from validation

I created several hidden customer patterns such as `stable`, `declining_engagement`, `support_issue`, `price_sensitive`, and `dormant`.

Those labels drive how the data is generated, but they are kept outside the application tables in a separate truth dataset.

That gave me a way to ask:

> Does a customer generated as declining actually look like they are declining?

The first answer was: not reliably.

Only about **46.7%** of the customers generated as `declining_engagement` showed the decline expected by the validation rule. The target was at least 75%.

The tables were valid. The foreign keys were correct. The generator ran successfully.

But the data was semantically wrong.

I changed the generator instead of lowering the test.

After the fix, the declining-behavior pass rate was above **91%** at the final scale test.

That changed how I think about synthetic data:

> A dataset can be structurally correct and still be useless for an AI application.

## Scale created another design change

I initially used CSV because it was easy to inspect.

As the dataset grew, validation and file I/O became the bottleneck. Rather than choosing a different format upfront, I changed the design after measuring the problem.

The scale path moved to Parquet and streaming-oriented validation.

The final benchmark generated:

- **100,000 customers**
- **478,253 orders**
- **3.58 million behavioral events**
- **27,414 support tickets**
- approximately **7 million production-like rows**

The run completed in about **42 seconds**, at roughly **166,000 rows per second**, producing about **240 MB** of Parquet data.

Structural and semantic validation both passed.

## Not all knowledge belongs in tables

The other half of the foundation was business knowledge.

SignalDesk will eventually need both customer facts and NovaCart policies.

These are different problems.

A question such as:

> How many orders did this customer place?

should come from deterministic structured data.

A question such as:

> What does NovaCart policy say about repeated shipping failures?

may require knowledge retrieval.

I generated 1,000 synthetic business documents containing current policies, superseded versions, drafts, incomplete guidance, playbooks, procedures, and FAQs.

I also deliberately left some questions unanswered.

For example, there is no authoritative document defining the perfect personalized discount or proving the causal effect of a retention offer.

That matters because a production AI system needs to recognize:

> I do not have enough authoritative evidence to answer this.

## What I learned

The biggest lesson from this milestone is that synthetic data should be treated like a product.

It needs contracts, validation, measurements, realistic failure modes, and known limitations.

I also learned not to optimize too early. CSV was fine until measurements showed otherwise. Parquet became justified by a real scale problem.

And I learned something that will matter later when I reach RAG: retrieval cannot solve missing knowledge. If an organization has important rules only in people's heads, Slack conversations, or inconsistent operating habits, the first job may be to discover and formalize that knowledge.

The foundation is now ready.

Next, I will turn this raw synthetic CDP into a deterministic customer-360 layer that SignalDesk can query.
