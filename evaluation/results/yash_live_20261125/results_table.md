# I Agent Hosted Test Results

Hosted model requested is `openai/gpt-oss-20b`. The agent used the teammate implementations in simulation on commit `64fc1855fd92cd9be8feea1666e8393da6084eac`. The plan requested one trial per case.

| Case | Result | Model | Answer source | Details |
| --- | --- | --- | --- | --- |
| T02 | PASS | openai/gpt-oss-20b | llm | All checks passed |
| T08 | FAIL | openai/gpt-oss-20b | llm | ordered_tools, user_claim_only, false_user_answer |
| T09 | FAIL | openai/gpt-oss-20b | llm | provenance_answer |
| T10 | FAIL | openai/gpt-oss-20b | llm | ordered_tools, automatic_recheck_observed, move_answer |
| T03 | PASS | openai/gpt-oss-20b | llm | All checks passed |
| T07 | PASS | openai/gpt-oss-20b | llm | All checks passed |
| B_APPROACH | FAIL | openai/gpt-oss-20b | llm | ordered_tools, object_detected_after_move |

7 scored runs with 3 passes, 4 failures and 0 fallback-summary passes. The batch also contains 0 provider interruptions and 0 incomplete attempts.

Provider interruptions and incomplete attempts are outside the scored totals. The agent generates `fallback_summary` from logged evidence. This batch records individual trials.
