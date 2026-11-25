# Live runs for Yash: T02, T03, T07, T08, T09, T10, B_APPROACH

Run from the repository root in PowerShell. The commands use only options the runner and summarizer
have (`--live`, `--tests`, `--repeats`, `--output-dir`, `--logs`). Never commit `.env` or the logs
(`evaluation/logs/` is gitignored).

## 1. Set up

```powershell
git checkout main
git pull origin main              # must include commit 64fc185 or later
copy .env.example .env            # then put GROQ_API_KEY=... in .env
# optional: LLM_FALLBACK_MODEL=<a model from: python -m scripts.list_available_models>
python -m pip install -r requirements.txt
```

## 2. Smoke test (no quota used)

```powershell
python -B -m evaluation.runner --fake --tests T02,T03,T07,T08,T09,T10,B_APPROACH --output-dir evaluation/logs/final/smoke
```

All seven should print `PASS`. If any does not, stop and report it before any live run.

## 3. Live runs, one test at a time

Check your Groq usage before each one. A run takes about 5 to 11 model calls, roughly 25 to 45k tokens
(an estimate; the logs do not record tokens). The daily limit is 200,000 tokens per key.

```powershell
python -B -m evaluation.runner --live --tests T02 --repeats 1 --output-dir evaluation/logs/final/yash-live
python -B -m evaluation.runner --live --tests T08 --repeats 1 --output-dir evaluation/logs/final/yash-live
python -B -m evaluation.runner --live --tests T09 --repeats 1 --output-dir evaluation/logs/final/yash-live
python -B -m evaluation.runner --live --tests T10 --repeats 1 --output-dir evaluation/logs/final/yash-live
python -B -m evaluation.runner --live --tests T03 --repeats 1 --output-dir evaluation/logs/final/yash-live
python -B -m evaluation.runner --live --tests T07 --repeats 1 --output-dir evaluation/logs/final/yash-live
python -B -m evaluation.runner --live --tests B_APPROACH --repeats 1 --output-dir evaluation/logs/final/yash-live
```

The order puts T02, T08, T09 and T10 first: they now need the history call, so they are the most likely
to hit the call limit. Each command adds new run folders, so the same `--output-dir` is fine.

## 4. Quota

- Seven tests, one run each, is about 200 to 280k tokens: more than one key allows. Split it: the first
  four tests on one key, the other three on a second key (or a teammate's key).
- Second repeats only if tokens are left: use `--repeats 2` in a command or a second batch.
- If a log shows `Daily limit reached` (HTTP 429), that run is **not a result**. Delete that run folder or
  mark it, and continue on another key.
- Do not run all tests in one batch command; a limit mid-batch wastes the remaining runs.

## 5. Summarize and send back

```powershell
python -B -m evaluation.summarize --logs evaluation/logs/final/yash-live --output-dir evaluation/results
Compress-Archive -Path evaluation/logs/final/yash-live -DestinationPath yash-live-logs.zip
```

- Send back `yash-live-logs.zip`, plus `evaluation/results/results_table.md` and `summary.json`.
- Check the zip does not contain `.env` before sharing.
- If results are in several folders, pass one `--logs <folder>` per folder.

## 6. Report along with the logs

- Which run folders were quota failures (excluded).
- Whether any run's `model` is not `openai/gpt-oss-20b` (the fallback model); report those separately.
- The `answer_source` of each run (`llm` or `fallback_summary`). A pass through the fallback summary is
  reported as a fallback, not as a model-written pass.

## 7. If tokens are left

Re-run T01, T04 and T06 once: they ran before the last two commits (limit of 12 calls and the check
wording change).

```powershell
python -B -m evaluation.runner --live --tests T01 --repeats 1 --output-dir evaluation/logs/final/yash-live
python -B -m evaluation.runner --live --tests T04 --repeats 1 --output-dir evaluation/logs/final/yash-live
python -B -m evaluation.runner --live --tests T06 --repeats 1 --output-dir evaluation/logs/final/yash-live
```

## What has been measured so far (single runs, `openai/gpt-oss-20b`)

| Test | Runs | Result |
|---|---|---|
| T01 | 1 | pass, model-written answer |
| T04 | 1 | pass, model-written answer |
| T06 | 1 | pass, model-written answer |
| T05 | 4 | 2 pass via `fallback_summary`, 1 fail on wording, 1 model-written pass |
| T02, T03, T07, T08, T09, T10, B_APPROACH | 0 | no live run on this code |
