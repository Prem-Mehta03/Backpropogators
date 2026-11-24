# Live demo UI

    python scripts/live_ui.py                 # real agent, real layers, needs GROQ_API_KEY like ask_agent.py
    python scripts/live_ui.py --replay        # backup: plays recorded runs, no model calls
    python scripts/live_ui.py --scenario scenario_b

Open http://127.0.0.1:8765. three.js r128 (MIT) is bundled in ui/live/three.min.js, so the page needs no internet.
Each live question also writes evaluation/logs/agent_run_live_<UTC>.json.
