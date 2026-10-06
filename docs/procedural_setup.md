# Procedural layer: setup and first proof (LLM client + one tool call)

## 1. The API key you need

Only **one** key: a **Groq API key** (Guidelines section 7 picks Groq as the host for an
open-weight 8B instruct model).

1. Go to https://console.groq.com/keys and sign in. Check the console for current free-tier limits.
2. Click **Create API Key**, name it `i-agent`, copy the value (shown once).
3. In the repo root: `cp .env.example .env`, then paste it:
   ```
   GROQ_API_KEY=gsk_...your key...
   LLM_MODEL=openai/gpt-oss-20b
   ```
4. Never commit `.env`, paste the key in chat, or put it in code. `.env` is git-ignored.

Groq retired `llama-3.1-8b-instant` (deprecated 16 Aug 2026; the API now answers
`model_not_found`). Its documented replacement is `openai/gpt-oss-20b`, an open-weight
20B model with tool calling, so that is the default. Model IDs on Groq change often: run
`python -m scripts.list_available_models` to see what your key can use, and set
`LLM_MODEL` in `.env` (no code change). Tell the team about the model, since Guidelines
section 7 names an 8B model.

Hosted tiers have rate limits. Tests with the scripted fake LLM use no quota at all.

No other key is needed. The sensor stub, memory stub and tests run offline.

## 2. Install and run

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m pytest -q                       # offline tests; the live test is skipped without a key
python -m scripts.list_available_models   # which model IDs your key can use
python -m scripts.check_llm_connection    # step 1: plain call, no tools
python -m scripts.ask_agent               # step 2: the route question, real model, saves a log
python -m scripts.ask_agent --stubs-only "What does your front LiDAR read?"
python -m scripts.ask_agent --no-entity-list   # hide the entity ids: reproduces the 'route' failure
```

Expected from step 2: log lines such as `tool=query_belief ok=True` and `tool=read_lidar
ok=True`, then the tools called, the number of model calls, the answer and the path of a
JSON log in `evaluation/logs/`. The log also records `known_subjects` and
`unknown_subjects_used` (memory lookups with an id outside the entity list). Exit code 0 means the model gave a final answer; 1 means a
run error (see the `error` line: `STEP_LIMIT` or `INTERNAL`).

Tools come from `scripts/tool_wiring.py`. The five memory tools are the methods of Vyom's
`BeliefMemory` (`declarative/belief_graph.py`), created fresh and seeded with the demo beliefs on
every run. The six sensor and action tools come from Asvin's `create_sensorimotor(scenario)`
(`sensorimotor/__init__.py`), which builds a fresh simulated world per run; pick the world with
`--scenario` (default `scenario_a`). Anything the real layers do not provide is filled in by the
fakes in `tests/procedural/fakes`. The log's `tool_sources` and `scenario` fields show what ran.
`--stubs-only` forces the fakes for everything.

Run the route question 3 to 5 times. An 8B model can skip the tool or send bad arguments
occasionally; note how often, because the evidence checklist and tool-call repair work are designed around that.

## 3. Quality checks before a pull request

```bash
black . && ruff check . && python -m pytest -q
```

Also confirm: no `print` inside `procedural/` (scripts may print), no key in `git diff`,
docstrings state inputs, outputs and error codes, temperature is 0.

## 4. Git and pull request

```bash
git checkout -b feature/prem-llm-client
git add procedural/ tests/procedural/ scripts/ docs/ .env.example requirements.txt
git status        # confirm contracts/models.py is NOT staged (it belongs to Vyom)
git commit -m "Add LLM client and single read_lidar tool-call proof"
git push -u origin feature/prem-llm-client
```

PR description: what it does, tests that cover it (`tests/procedural/`), the log of one
real run, reviewer named (per the 3-Day Plan, Vyom for the procedural layer). If you skip
adding a requirement or file the Guidelines expect, give one line explaining why.

## 5. First real run: failure list

After running the route question with the real model, copy `docs/first_run_failure_list.md`
and fill one row per failure, naming the layer where it started (Guidelines section 8).

## 6. Definition of done for the agent-loop step

- [ ] `python -m pytest -q`, black, ruff and pyright are clean.
- [ ] `scripts.ask_agent` runs the route question against the real model and saves a log.
- [ ] Step limit and bad-model-output cases are covered by tests (they are, in test_agent.py).
- [ ] Failure list filled in, each item with a layer and an owner.
- [ ] No secrets and no placeholders committed; PR open with a named reviewer.

## Rules enforced in code (checklist and provenance guard)

- **Evidence checklist** (`procedural/checklist.py`, run by `agent.py`): a final answer is
  refused until `query_belief` and one sensor tool were attempted. A lookup that returned
  NOT_FOUND or SENSOR_UNAVAILABLE counts (the layer was asked); INVALID_ARGUMENT and INTERNAL do
  not. Refusals are counted in `evidence_nudges`. Pass `required_evidence=()` to switch it off.
- **Provenance guard** (`procedural/update_guard.py`): `downgrade_belief` needs a belief id
  returned by a lookup in this run and a lower confidence; a sensor `update_belief` needs a
  sensor actually read in this run and takes its confidence from that reading. Refusals and
  overrides appear under `guard` in the run log.
- Conflict priority stays in Vyom's `declarative/conflicts.py`; sensor-to-belief conversion
  stays in Asvin's adapter. The procedural layer does not decide who wins.
