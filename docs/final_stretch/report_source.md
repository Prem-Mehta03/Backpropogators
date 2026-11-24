# Architecture Verification Report Source

`build_report.py` contains the editable report text, structure, tables and figures. It uses ReportLab and reads the final summary and named logs from the repository root. The default Figure 3 is a vector illustration derived from the T05 glass frame. Supply the offline T05 replay still using `--screenshot` to use the rendered frame. Preserve that still with the local review artifacts so another person can rebuild the PDF.

```powershell
python -B docs/final_stretch/build_report.py --logs evaluation/logs/final/verified_20261123 --screenshot docs/final_stretch/t05_replay_still.png --screenshot-run 20261123T052100961327Z-01 --viewport 89 390 974 328 --output evaluation/logs/role4/I_Agent_Architecture_Verification_Report.pdf
pdfinfo evaluation/logs/role4/I_Agent_Architecture_Verification_Report.pdf
```

Use an interpreter with ReportLab available. To regenerate on a reviewed branch, tag or commit, pass the confirmed GitHub ref with `--revision`; the report then links to the corresponding results table. After the team confirms the final tag, update the pending review sentence in `build_report.py` and render again. The layout enforces four A4 pages with 2 cm margins and 11 pt body text. When revising, tighten wording before changing the page styles.

The layer sections distinguish authored draft sections from published team review. Each reviewer should check their section against the current contracts, tool traces, and results before the team submits it. The 30 scored offline trials use the scripted model. Replace live denominators only after collecting comparable final hosted receipts and rerunning the summary generator.
