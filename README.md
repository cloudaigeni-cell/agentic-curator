# agentic-curator

A hands-on multi-agent framework in Python: **one orchestrator, six specialised subagents, and every file operation behind a real MCP server.** It curates a messy library of documents and photos — finds duplicates, merges same-subject notes, and retires the leftovers reversibly.

It is built to be read. Each file opens with what it teaches, and the demo runs with no API key.

**Open [`docs/architecture.html`](docs/architecture.html) in a browser first** — it is an interactive 3D model of the system that steps through a real run.

```
            ┌───────────────────────────┐
  layer 4   │  Orchestrator  ·  Bus     │   owns the plan, touches no file
            └────────────┬──────────────┘
  layer 3   Year×N  Document  Duplicate  Photo  Consolidator  Deletion
            └────────────┬──────────────┘
  layer 2   Blackboard · Policy gate · LLM provider · MCP client
            └────────────┬──────────────┘   JSON-RPC 2.0 over stdio
  layer 1   MCP server "curator-library" — 8 tools, sandboxed
            └────────────┬──────────────┘
  layer 0   documents/   photos/   curated/   .curator_trash/
```

## Quick start (WSL, Linux or macOS)

```bash
git clone https://github.com/cloudaigeni-cell/agentic-curator
cd agentic-curator
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

curator doctor            # check the environment
curator demo              # build a sample library, plan only — nothing changes
curator demo --execute    # apply the plan: 8 files move to .curator_trash/
curator restore --library demo_library   # put them all back
pytest                    # 17 tests, including a real MCP server process
```

On your own folder:

```bash
curator run --library /mnt/c/Users/you/Documents/archive            # plan
cat runs/<run-id>/report.md                                          # review
curator run --library /mnt/c/Users/you/Documents/archive --execute   # apply
```

## The agents

| Agent | Task kind | Job | Can it remove files? |
| --- | --- | --- | --- |
| Orchestrator | `pipeline.run` | Inventory, fan out, sequence, vet the plan | No |
| Year agent (one per year) | `year.analyse` | Fingerprint one year's files, in parallel | No |
| Document agent | `doc.extract` | Text and PDF extraction, subject keys | No |
| Duplicate finder | `dup.documents` | Byte-identical and near-identical documents | No — proposes |
| Photo finder | `dup.photos` | Perceptually identical photos | No — proposes |
| Consolidator | `consolidate.subjects` | Merge same-subject notes, verify, propose | No — proposes |
| Deletion agent | `delete.execute` | Move approved files to trash | **Yes, and only this one** |

## Choosing a model

The framework runs fully offline: deterministic code does all the measuring. A model only adds judgement (better subject names, a second opinion on the plan).

| Provider | Set | Install |
| --- | --- | --- |
| `offline` (default) | nothing | — |
| `anthropic` | `ANTHROPIC_API_KEY` | `pip install -e ".[anthropic]"` |
| `gemini` (API key) | `GOOGLE_API_KEY` | `pip install -e ".[gemini]"` |
| `gemini` (Google credentials) | `gcloud auth application-default login`, `GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT` | `pip install -e ".[gemini]"` |
| `openai` / local Ollama | `OPENAI_API_KEY`, optional `OPENAI_BASE_URL` | `pip install -e ".[openai]"` |

```bash
cp .env.example .env      # fill in one provider
CURATOR_PROVIDER=anthropic curator demo --fresh
```

## Safety, in one paragraph

Dry run is the default. Agents that find things can only *propose*, with evidence. Proposals pass a policy gate (confidence floor, protected paths, batch cap, a named survivor). Approval is a hash of the exact plan, so a plan that changes after review is refused. The MCP server has no delete tool — only `move_to_trash`, with a manifest — and rejects any path outside the library. See [`core/policy.py`](src/agentic_curator/core/policy.py).

## Learn it

1. [`docs/visual-guide.html`](docs/visual-guide.html) — the build manual: one 3D diagram per phase
2. [`docs/architecture.html`](docs/architecture.html) — the whole system as one 3D model you can step through
3. [`docs/01-concepts.md`](docs/01-concepts.md) — agents, tasks, the blackboard, why no agent chat
4. [`docs/02-mcp-primer.md`](docs/02-mcp-primer.md) — what MCP is, on the wire, with this server
5. [`docs/03-lab-guide.md`](docs/03-lab-guide.md) — eight practical labs
6. [`docs/04-wsl-setup.md`](docs/04-wsl-setup.md) — WSL specifics
7. [`docs/05-google-drive.md`](docs/05-google-drive.md) — pointing the agents at Google Drive
8. [`docs/06-field-run.md`](docs/06-field-run.md) — a real Google Takeout run from WSL, problems and fixes

Then read the code in this order: `runtime.py` → `agents/orchestrator.py` → `core/bus.py` → `core/policy.py` → `mcp_layer/`.

## Layout

```
src/agentic_curator/
  runtime.py        wiring — the map of the system
  cli.py            the `curator` command
  core/             messages, agent base, bus, blackboard, policy, tracing
  agents/           orchestrator + six subagents
  mcp_layer/        MCP client registry, and the bundled MCP server
  llm/              provider interface + offline/Anthropic/Gemini/OpenAI
  tools/            pure functions: hashing, PDF text, dHash, Jaccard
  sample.py         builds the planted demo library
tests/              tools, policy, end-to-end pipeline
docs/               3D field guide + written guides
scripts/run_wsl.sh  one-command dry run from WSL against a Takeout part on D:\
```

MIT licensed.
