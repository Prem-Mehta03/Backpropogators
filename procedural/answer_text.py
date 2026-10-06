"""Typographic clean-up of the model's final answer (a rule in code, not in the prompt).

Models sometimes swap plain characters for look-alikes: a non-breaking hyphen inside an ISO
date, or a narrow no-break space before "cm". The tool data is untouched, but the answer text
then no longer matches it character for character. This module undoes only those swaps.
It never changes words or numbers, and it leaves dashes used in ordinary prose alone.
"""

from __future__ import annotations

import re

# U+2010..U+2015 are hyphen, non-breaking hyphen, figure dash, en dash, em dash and horizontal
# bar; U+2212 is the minus sign. Inside YYYY?MM?DD they can only be a mangled "-".
_DASHES = "‐-―−"
_ISO_DATE = re.compile(rf"(\d{{4}})[{_DASHES}](\d{{2}})[{_DASHES}](\d{{2}})")
_ODD_SPACES = re.compile("[  ]")


def normalize_answer_text(text: str) -> str:
    """Replace look-alike characters with the plain ones the tools used.

    Inputs: the model's answer text. Output: the same text with (1) dash variants inside
    YYYY-MM-DD dates turned into "-" and (2) no-break and narrow no-break spaces turned into
    ordinary spaces. Prose dashes, words and numbers are unchanged.
    """
    text = _ISO_DATE.sub(r"\1-\2-\3", text)
    return _ODD_SPACES.sub(" ", text)
