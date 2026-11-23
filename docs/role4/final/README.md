# Role 4 Evaluation and Historical Evidence

For the current v1.1 acceptance suite and its results, start with the [final stretch review guide](../../final_stretch/README.md). The S01–S10 runner remains available as a regression suite. Its canonical Scenario A and B paths now share the v1.1 acceptance seeds. The earlier reference path and the archived measurements retain their original fixtures.

The 20 November PR #3 baseline recorded 50/50 reference passes and **40/50 behavior passes across 50 planned canonical or mixed cases**. Of those, 45 attempts were eligible for the behavior result, giving **40/45 eligible passes**. Five scoped S07 unsupported-temperature probes passed their diagnostic checks and remain separately counted. Combining them produced the historical 45/50 raw verdict count. S09 failed all five attempts on that baseline, and three canonical controls reproduced known failures. The 405-test count and [verification record](verification.json) describe that earlier checkout.

| Start here | Use it for |
| --- | --- |
| [Historical architecture verification report](report.md) | Read the implementation and evidence at the PR #3 baseline |
| [Historical verification](verification.json) | Check the 20 November build, test counts and observed gaps |
| [Demo and package runbook](demo_runbook.md) | Reproduce the trials, view Scenario A and B, and build or verify the archive |
| [Failure analysis](failure_analysis.md) | Trace failures to their observed boundary and record a new finding |
| [Review packet](review_packet.md) | Cross-check the evidence, settle fixture decisions and record team review |
| [Contribution file list](contribution_files.txt) | See the files in this Role 4 contribution |

For the 20 November ZIP, `evidence/summary.json` has counts and case metadata, and `evidence/metrics.csv` has per-case repeated pass rates. For current acceptance, GitHub reviewers can inspect the [results table](../../../evaluation/results/results_table.md) and the [individual T-case logs and replay traces](../../../evaluation/logs/final/verified_20261123/). Earlier Role 4 captures remain under [teammate integration](../teammate_integration/README.md) and [mid-project preparation](../PROGRESS_REPORT_NEW_PHASE_D.md).
