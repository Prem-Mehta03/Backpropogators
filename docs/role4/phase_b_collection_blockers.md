# Phase B collection-blocker diagnosis

Both blockers are unchanged at the canonical base plus the preserved Phase A
contribution. No official namespaces were populated with dummy modules, no
teammate tests were altered, and no tests were ignored to obtain a pass.

| Test module | Exact exception | Import/dependency chain | Concrete cause |
| --- | --- | --- | --- |
| `tests.procedural.test_single_tool_call` | `ModuleNotFoundError: No module named 'contracts'` (`exc.name='contracts'`) | test_single_tool_call.py:11 → procedural.single_tool_call:19 → procedural.tools:14 → contracts.models.ToolResult | Missing official Vyom-owned contracts package/models |
| `tests.procedural.test_tools` | Same exception and missing name | test_tools.py:7 → contracts.models.ToolResult; procedural.tools also imports it | Same missing official contracts, not a Role 4 import issue |

Direct import probes also establish:

- `import contracts.models` fails with `No module named 'contracts'`.
- `import sensorimotor.stub` fails with `No module named 'sensorimotor'`.
- `procedural.tools` and `procedural.single_tool_call` each fail through contracts.
- `procedural.llm_client` and `tests.procedural.scripted_llm` import correctly from
  the clone and support the available offline client path.

The blocked tests additionally import `from sensorimotor import stub` and bind
`stub.read_lidar` at collection. This missing teammate test fixture is masked by
the earlier contract failure. It is not an installed-package problem. Current
pytest/pydantic/dotenv are installed; openai is absent but only imported by the
non-injected client constructor. The Phase A tests package marker already fixes
the earlier production/test procedural name collision; no such collision remains.

## Exact pending teammate change

Vyom must publish the approved `contracts/models.py` (plus package/version/
validators as required) exposing `ToolResult`, ToolError and the authoritative
schema. Prem currently calls `ToolResult(...)`, `ToolResult.model_validate(...)`
and `.model_dump()`, with tool/ok/data/error/timestamp and fixed error codes. No
schema definition is proposed or synthesized by Role 4.

Asvin and Prem must decide the published offline sensor fixture path. Both blocked
test modules currently require `sensorimotor.stub.read_lidar(direction="front")`:
an approved envelope whose front data includes value 12, status blocked and
sensor lidar_front, with an INVALID_ARGUMENT envelope for direction left.
If the approved public implementation instead is `sensorimotor.sensors.read_lidar`
with that compatible deterministic fixture, the precise candidate Prem-owned
test patch is:

```diff
-from sensorimotor import stub
+from sensorimotor.sensors import read_lidar
-REGISTRY = {"read_lidar": stub.read_lidar}
+REGISTRY = {"read_lidar": read_lidar}
```

In test_tools.py, its direct `stub.read_lidar()` call would likewise become
`read_lidar()`. Apply only after Asvin confirms the real function and deterministic
fixture semantics; otherwise Prem should use Asvin's published approved test
fixture. This proposed patch is **pending, not applied**. Publishing an import
alone cannot justify weakening assertions or using incompatible sensor data.

Retest both exact modules after owner publication. Do not copy historical Role 4
dataclasses into `contracts/` or register fake `sys.modules` shims. The complete
single-tool path remains blocked and is not reported integrated in Phase B.
