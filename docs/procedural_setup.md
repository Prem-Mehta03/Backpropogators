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
python -m scripts.run_lidar_tool_call     # step 2: the gate check
```

Expected from step 2: log lines showing `tool=read_lidar ok=True`, a JSON dump of the
tool call (value 12, unit cm, status blocked) and a final answer that quotes those values.
Exit code 0 only if the model really called a tool.

Run the gate check 3 to 5 times. An 8B model can skip the tool or send bad arguments
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
git status        # confirm contracts/models.py and sensorimotor/stub.py are NOT staged
git commit -m "Add LLM client and single read_lidar tool-call proof"
git push -u origin feature/prem-llm-client
```

PR description: what it does, tests that cover it (`tests/procedural/`), the log of one
real run, reviewer named (per the 3-Day Plan, Vyom for the procedural layer). If you skip
adding a requirement or file the Guidelines expect, give one line explaining why.

## 5. Definition of done for this step

- [ ] `check_llm_connection` returns a reply from the real model.
- [ ] `run_lidar_tool_call` shows the model calling `read_lidar` and quoting 12 cm / blocked.
- [ ] Offline tests pass; black and ruff clean.
- [ ] No secrets and no placeholders committed; PR open with a named reviewer.
