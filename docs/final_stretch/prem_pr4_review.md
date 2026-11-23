# Role 4 Review of Prem PR 4

Reviewed [PR 4](https://github.com/Prem-Mehta03/Backpropogators/pull/4) at
`e11d065b6a16e849f13cda204c25d34a99d19ee3`. The request to Yash covers
the two Role 4 files changed by Prem and using `FrameRecorder` in the
acceptance runner.

The unchanged PR head passed 191 Role 4 tests and 179 subtests with no
blocked network attempts. The combined candidate also exercises the
new v1.1 contracts and exact T01–T10 scenarios.

- The old S08 expectation of 11 cm actual movement is historical. In the
  candidate, the requested motion is rejected before dispatch, the
  automatic 12 cm LiDAR receipt is preserved, the move returns
  `CONFLICT`, and the pose stays at x=0.
- Dispatch evidence is matched on request ID and tool. An automatic read
  can share the model's move ID, but cannot be counted as dispatched
  movement. The runner compares automatic boundary receipts against the
  move guard's recheck receipts.
- `evaluation/runner.py` captures frame zero and passes
  `FrameRecorder.on_step` through an observer that also preserves the raw
  tool envelope and automatic flag. T10 separately checks its changed
  scene and the refused move.
- The candidate extends the guards to reject a contradictory value or
  subject even when the model cites a genuine sensor source. It also
  requires and logs the enabled ultrasonic check. These fixes are kept
  in the candidate for review by the procedural owner.

This note records local technical review and verified changes. The
GitHub review and the final team release gate are separate.
