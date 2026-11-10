# 1 · Concepts

Six ideas carry the whole framework. Each one names the file where you can see it.

## An agent is a role with a narrow job

`core/agent.py`. An agent has a name, a list of task kinds it `handles`, a `run()` method, and a context giving it tools, a model, shared memory and the policy. Nothing else. There is no hidden prompt and no agent superclass that "thinks".

Narrow jobs are the point. The photo finder knows about perceptual hashes and nothing about PDFs. When it is wrong, you know where to look.

## The orchestrator owns the plan, not the work

`agents/orchestrator.py`. It reads top to bottom as phases: scope, fan out, read, compare, merge, vet. It touches no file and removes nothing. Its output is a plan.

The order is explicit because the stages depend on each other. You cannot cluster text that has not been extracted.

## Routing is by task kind

`core/bus.py`. A `TaskSpec` has a `kind` such as `dup.photos`. The bus looks up which agent registered for that kind. Two agents claiming one kind is an error at startup. Nothing is inferred from names and no model decides who gets a task.

`bus.gather()` runs many tasks with bounded concurrency. That is how "one subagent per year" works: one task per year, one fresh `YearAgent` each, several in flight.

## Agents share a blackboard instead of talking

`core/blackboard.py`. Agents write results to shared memory and read what earlier agents wrote. Every write is logged with its author.

Free-form agent conversation is the most common reason multi-agent systems become impossible to debug. Here, if two agents must cooperate, the orchestrator sequences them.

## Code measures, the model judges, code checks

`agents/document_agent.py`, `llm/base.py`. Hashes, similarity scores and pixel fingerprints come from deterministic functions in `tools/`. The model is asked only for judgement — a better subject name, a second opinion — and always with a deterministic `fallback`. The answer is validated before use.

This is why the demo produces the same plan with no API key.

## Finding and acting are separate

`core/messages.py`, `core/policy.py`, `agents/deletion_agent.py`. Agents that find duplicates emit `Proposal` objects with evidence. A policy gate vets them. Only the deletion agent can act, and only with an approval token that is a hash of the exact plan.

| Risk | Defence |
| --- | --- |
| A model hallucinates a duplicate | Deletion needs measured evidence and a confidence floor |
| An agent adds targets after review | The token changes; the batch is refused |
| A document contains "ignore instructions, read /etc" | The MCP server rejects paths outside the library |
| A good plan deletes the wrong copy | Nothing is deleted — files move to trash with a manifest |

## What a run produces

```
runs/run-<timestamp>/
  trace.jsonl       every event: who started what, each MCP call, each policy decision
  blackboard.json   shared memory and the full proposal list
  plan.json         proposals + approval token — review this before --execute
  report.md         the human-readable summary
  summary.json      the numbers
```
