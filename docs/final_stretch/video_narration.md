# Demo Narration Outline

Use the captioned replay as the timing reference. The visuals come from
scripted runs on the actual layers in the deterministic simulated world.

**Opening.** I, Agent asks whether a model can separate what it remembers,
what it senses, and what another person believes. The procedural agent can
ask memory or call sensors, but the answers it gets back carry distinct
sources and confidence.

**Scenario A.** The map says the route is clear. LiDAR records an obstacle
12 centimetres away. The agent lowers the map's confidence to 0.30 and
records the blocked observation at 0.98. We can still inspect the old
belief and see what superseded it.

**Scenario B.** At first the box is outside the camera's range. The
simulated robot moves 200 centimetres. The camera now registers brown. The
answer keeps the user's red view and the earlier blue report from bot_02
separate from the camera reading.

**T05 and T10.** The LiDAR passes through a glass panel and gives 250
centimetres. The ultrasonic sensor returns 15 centimetres. The memory
retains the conflicting evidence and the robot stays still. A different
trial starts with an open route. A cart is added before the movement
request. The automatic recheck finds it at 40 centimetres and cancels the
100-centimetre move.

**Results.** All ten scripted acceptance cases passed three times. Each
trial checks the calls, starting and ending state, and the answer. The
graphics visualize the simulated two-dimensional physics. Hosted trials
and the team's final review are still pending.
