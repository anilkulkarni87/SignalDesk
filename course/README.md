# SignalDesk Learning Edition

> Learning scope: SignalDesk is a synthetic educational system. The course
> teaches engineering decisions and evidence discipline; it does not provide a
> production product or evidence of real customer impact.

SignalDesk is a project-based AI engineering course built around one cumulative
system. Instead of presenting isolated examples, it follows the same synthetic
customer-intelligence workflow from discovery through data, LLMs, retrieval,
agents, operations, and FDE delivery.

## Start in five minutes

Course navigation and frozen artifact checks use the Python standard library.
From the repository root:

```bash
python run_course.py doctor
python run_course.py audit
python run_course.py list
python run_course.py start 01
```

Read the lesson printed by `start`, inspect the referenced implementation and
evidence, and then run:

```bash
python run_course.py check 01
python run_course.py complete 01 \
  --reflection "I can explain why the workflow and metric come before the model."
python run_course.py next
```

Progress is written to an untracked `LEARNING.md` in the repository root.
Automated checks verify technical artifacts. A learner reflection records what
was understood; passing a test alone never means the concept was learned.

The retrieval, agent, and capstone lessons also run their existing test suites.
Install the current development environment before those labs:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-commit17-dev.txt
```

An OpenAI key is not required for any course check. It is needed only when a
learner deliberately chooses an optional live-model experiment.

## Pilot path

The first course increment contains six anchor lessons:

| Lesson | Topic | Outcome |
|---|---|---|
| 01 | Problem-first FDE discovery | Turn workflow pain into a measurable hypothesis |
| 02 | Synthetic customer data | Build safe data whose behavior can be validated |
| 04 | Structured LLM evaluation | Cross the deterministic/probabilistic boundary |
| 06 | Retrieval from first principles | Compare retrieval quality and latency |
| 10 | Bounded agent loops | Treat tools and stopping conditions as contracts |
| 18 | FDE capstone | Present evidence, limitations, and the next decision |

The complete 18-lesson map is in [curriculum.json](curriculum.json). Lessons not
yet converted are marked `planned`; the CLI does not pretend they are ready.

## Lesson loop

Every lesson follows the same learning contract:

```text
PROBLEM -> FIRST PRINCIPLES -> BUILD -> MEASURE -> BREAK -> EXPLAIN -> SHIP
```

- **Problem:** name the workflow constraint before choosing technology.
- **First principles:** identify the smallest underlying engineering idea.
- **Build:** inspect or implement the bounded capability.
- **Measure:** run a deterministic check or read a frozen experiment.
- **Break:** examine a failure, regression, or tradeoff.
- **Explain:** state the decision in your own words.
- **Ship:** keep a reusable artifact for the final capstone.

## Zero-call checks

Course verification never calls a model. It reads frozen reports and runs local
tests. Live experiments remain optional and retain the accepted configuration:

```text
model             gpt-5.6-luna
reasoning effort  none
```

## Course versus product

The existing `src/`, `evals/`, `tests/`, `web/`, and Git history remain the
canonical implementation. The course links to those artifacts rather than
copying solution code into lesson folders. Later starter tags can expose
historical build states without creating a second application.
