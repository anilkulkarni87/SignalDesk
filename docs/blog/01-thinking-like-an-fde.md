# Thinking Like an FDE: Starting With the Workflow, Not the LLM

When I decided to learn the skills required to become a Forward Deployed Engineer, I didn’t want the journey to be purely theoretical. I wanted to learn by building something step by step.

Since my background is in Customer Data Platforms and customer data engineering, I decided to build on what I already know. That idea became **NovaCart**, a fictional e-commerce company, and **SignalDesk**, the system I’ll build throughout this learning journey.

## My first instinct was wrong

NovaCart has a retention problem. Around **2,000 customers are identified as at risk every week**, but investigating one customer takes approximately **20–30 minutes**. As a result, only about **15% of those customers are actually investigated**.

My immediate thought was:

> Let’s build a churn agent.

But as I thought more carefully about the problem, I realized NovaCart already had a model identifying at-risk customers.

So churn prediction was not really the bottleneck.

The actual problem was everything that happened afterward.

A Retention Specialist still needed to understand the customer’s purchase history, behavior, email engagement, and support interactions before deciding what to do.

That reframed the problem from:

> Who is likely to churn?

to:

> What is happening with this already at-risk customer, and what should we do about it?

## The product changed with the problem

Once the problem changed, the product changed too.

SignalDesk would investigate the customer, surface relevant evidence, and recommend one of three possible interventions:

- `NO_ACTION`
- `RETENTION_OFFER`
- `ESCALATE_TO_SUPPORT`

The recommendation would not automatically trigger an action.

Instead:

```text
Investigation
→ Evidence
→ Recommendation
→ Human Review
→ Final Decision
```

Human review matters because it keeps consequential decisions under specialist control. It also creates a useful feedback signal.

By recording whether specialists approve, modify, or reject recommendations, we can later measure how often SignalDesk’s recommendations align with human judgment.

## I deliberately avoided choosing tools

At this stage, I did not immediately think about LLMs, RAG, LangGraph, vector databases, or agent frameworks.

I wanted to stay close to the business problem first.

That forced me to think about:

- who the users are,
- what decisions they own,
- what workflows they follow,
- what the system must support,
- and how success should be measured.

From this exercise, I identified Retention Specialists, Retention Managers, and Customer Support Specialists as different personas with different responsibilities.

I also created workflows, requirements with acceptance criteria, success metrics, and a V0 architecture—all before selecting implementation technologies.

## The main lesson

The biggest lesson from this first milestone was simple:

> **Do not dive into the solution immediately.**

The problem initially presented may not be the problem that actually needs solving.

“Build a churn agent” sounded reasonable at first. But discovery showed that NovaCart already knew which customers were at risk. The real bottleneck was investigating those customers efficiently and making informed intervention decisions.

Starting with the workflow gave me a clearer problem, measurable outcomes, and an architecture grounded in actual needs.

The principle I want to carry through the rest of this project is:

> **Understand the workflow, define the outcome, measure the baseline, and only then choose the technology.**

Next, I’ll build the synthetic customer-data foundation underneath SignalDesk.
