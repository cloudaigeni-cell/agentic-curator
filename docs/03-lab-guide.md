# 3 · Lab guide

Eight labs, in order. Each changes one thing so its effect is visible in the trace. Start from a fresh demo each time:

```bash
curator restore --library demo_library 2>/dev/null; curator demo --fresh
```

## Lab 1 — Watch a run

```bash
curator demo
grep '"channel": "agent"' runs/*/trace.jsonl | tail -20
```

Find: how many `year.analyse` tasks ran, which finished first, and how many MCP calls the run made. Expected: 4 year tasks, 12 tasks in total, 41 MCP calls.

## Lab 2 — Speak MCP by hand

```bash
curator tools --library demo_library
```

Then write ten lines of Python using `MCPRegistry` and `ServerSpec.library()` to call `hash_item` on two files and compare. No agent is involved. This is all an agent's "tool use" is.

## Lab 3 — Break the sandbox

Call `read_text` with `../../etc/passwd`, then with `/etc/passwd`. Both must fail. Read `_safe()` in `library_server.py` and explain why a symlink inside the library pointing outside it is also refused.

## Lab 4 — Tamper with a plan

```bash
pytest tests/test_policy.py -k changed_plan -v
```

Then change `plan_token()` in `core/policy.py` to hash only the *number* of proposals. Run the test again and watch it fail. Restore the code. You have just seen why approval must bind to content.

## Lab 5 — Add a tool

In `library_server.py` add:

```python
@server.tool(description="Word count of a document.")
def count_words(path: str) -> dict[str, Any]:
    return {"path": path, "words": len(extract_text(_safe(path)).split())}
```

Run `curator tools --library demo_library`. The tool appears with a schema you never wrote.

## Lab 6 — Add a seventh agent

Create `agents/large_file_agent.py`:

```python
class LargeFileAgent(BaseAgent):
    handles = ("review.large",)
    name = "large-file-agent"

    async def run(self, task):
        records = await self.ctx.blackboard.get("records", [])
        big = [r.path for r in records if r.size > task.payload.get("bytes", 50_000_000)]
        await self.ctx.blackboard.propose([
            Proposal(action="review", targets=big, reason="large file", proposed_by=self.name)
        ] if big else [])
        return {"large_files": len(big)}
```

Register it in `runtime.py` and dispatch `task.child("review.large", {"bytes": 10_000})` from the orchestrator after phase 1. Nothing else changes. Check it in `curator agents`.

## Lab 7 — Plug in a model

```bash
pip install -e ".[anthropic]"      # or [gemini] / [openai]
export ANTHROPIC_API_KEY=...        # or the provider you have
CURATOR_PROVIDER=anthropic curator demo --fresh
grep '"channel": "llm"' runs/*/trace.jsonl | tail
```

Compare `plan.json` with the offline run. The delete proposals should be the same: the model changes subject names and the review, never the measurements. If they differ, find out why before trusting either.

## Lab 8 — Swap the server

Read `docs/05-google-drive.md`. Connect a second server in `runtime.py` under the name `drive`, and write an agent that calls `ctx.mcp.call("drive", ...)` to list files. Agents know tool names, not storage systems.

## Stretch goals

- Make the orchestrator's phase list come from the model, constrained to registered task kinds, with the fixed list as fallback.
- Add a `--approve TOKEN` flag so planning and execution are separate invocations.
- Replace dHash with pHash and measure false positives on your own photos.
