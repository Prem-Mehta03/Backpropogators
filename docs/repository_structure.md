# Repository structure: I, Agent

Follows Team_Guidelines section 3. The three layers are independent packages; the only
shared code is `contracts/`. Files marked **(Prem)** are the procedural layer.

```
i-agent/
├── contracts/                  Vyom   shared Pydantic models (the only shared code)
│   ├── models.py                      Belief, SensorReading, ToolResult, ToolError
│   ├── version.py                     schema_version constant
│   └── validators.py
├── declarative/                Vyom   beliefs and provenance
│   ├── belief_graph.py                NetworkX graph
│   ├── database.py                    SQLite provenance log
│   └── conflicts.py                   evidence-priority rules (in code, not in prompts)
├── sensorimotor/               Asvin  simulated world
│   ├── mock_env.py
│   ├── sensors.py                     read_lidar, read_camera, get_position
│   └── actions.py                     move_forward, move_backward, turn
├── adapters/                   Asvin
│   └── sensor_to_belief.py            the only place a reading becomes belief evidence
├── procedural/                 Prem   the LLM agent
│   ├── llm_client.py          (Prem)  talks to the hosted model; returns LLMResponse
│   ├── prompts.py             (Prem)  ALL prompt text lives here and only here
│   ├── tools.py               (Prem)  tool schemas, argument checks, ToolResult handling
│   ├── single_tool_call.py    (Prem)  one question, one tool round (proof of plumbing)
│   ├── state.py               (Prem)  agent state                       [next]
│   └── agent.py               (Prem)  ReAct loop, step limit, checklist [next]
├── evaluation/                 Vyom (logger.py) / Yash (runner.py)
│   ├── logger.py
│   ├── runner.py
│   └── logs/                          one JSON log per test run
├── tests/                      Yash (shared) + each owner's own tests
│   ├── scenarios.py, test_grounding.py, test_perspective.py, test_contracts.py
│   └── procedural/            (Prem)
│       ├── scripted_llm.py            fake LLM that replays fixed replies
│       ├── test_llm_client.py
│       ├── test_tools.py
│       └── test_single_tool_call.py
├── scripts/                    small runnable checks (proposed addition, see below)
│   ├── check_llm_connection.py        key + model + network work?
│   └── run_lidar_tool_call.py         real model -> read_lidar -> answer
├── demo/                       Asvin
│   └── app.py
├── docs/                              report sections, diagrams, this file
├── README.md, requirements.txt, pyproject.toml, .env.example, .gitignore
```

## Rules that shape the layout

- **No reaching across layers.** `procedural/` never imports `declarative/` or
  `sensorimotor/`. Tool functions are *passed in* (a registry dict), so the agent only
  ever calls published functions. `scripts/run_lidar_tool_call.py` is the one place that
  wires two layers together, like the future `evaluation/runner.py`.
- **`contracts/` is read-only for everyone except Vyom.** Procedural imports it, never edits it.
- **Secrets:** `.env` is git-ignored; only `.env.example` is committed.
- **Branches:** `main` always runs. Work on `feature/prem-<short-name>`, one topic per PR,
  nobody merges their own PR.

## Two items to confirm with the team

1. `scripts/` is not in Guidelines section 3. It is a small, useful addition (setup checks
   anyone can run), but ask Yash before the PR lands.
2. `pyproject.toml` sets black and ruff line length to 100 (black's default is 88). Yash owns
   repo setup; agree on one value so everyone's formatter agrees.

## Placeholders: do NOT commit these

Two files exist only so your code runs before teammates publish theirs. They are not yours:

| Local placeholder | Real owner / real file | Delete when |
|---|---|---|
| `contracts/models.py` | Vyom: `contracts/models.py` | Vyom's contracts are on `main` |
| `sensorimotor/stub.py` | Asvin: `sensorimotor/sensors.py` | Asvin's stub is on `main` |

When pulling `main`, keep theirs. If a field name differs from the placeholder, theirs wins
and our code or tests change, never the contract (Guidelines section 9).
