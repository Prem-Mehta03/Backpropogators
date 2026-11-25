"""The prompt version must change whenever the prompt text changes.

Why: live logs record PROMPT_VERSION so a result can be tied to its prompt. Round 3 of the T04/T05/T06
runs was logged as "v6.2" although the text had changed, because black had reformatted the line and a
later search-and-replace of the version string silently matched nothing. This test fails if the text
changes without a new version (and a new line here), or if a version is reused for different text.
"""

from __future__ import annotations

import hashlib

from procedural.prompts import PROMPT_VERSION, SYSTEM_PROMPT

# version -> sha256 of SYSTEM_PROMPT. Add a line when you change the prompt; never edit an old one.
PROMPT_HASHES = {
    "v6.3": "2b8e78b3a9b918c15cbc3820cb63e47ee1553ca8200e13d91ab92f4beec97b04",
    "v6.4": "7cbfe56f5560359e554fa494baf41e7d7554face2ba5917c154966fb543cee94",
}


def test_the_prompt_text_matches_its_recorded_version() -> None:
    assert (
        PROMPT_VERSION in PROMPT_HASHES
    ), f"PROMPT_VERSION {PROMPT_VERSION!r} has no hash here: add it after changing the prompt"
    digest = hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()
    assert (
        digest == PROMPT_HASHES[PROMPT_VERSION]
    ), "The prompt text changed but PROMPT_VERSION did not: bump it and add its hash"
