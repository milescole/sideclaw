"""Scan memory content for prompt injection patterns before writing."""

import re

_INJECTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"you are now|from now on you", re.I), "role hijack"),
    (re.compile(r"ignore (all )?(previous|above|prior)", re.I), "instruction override"),
    (re.compile(r"disregard (all )?(previous|above|prior)", re.I), "instruction override"),
    (re.compile(r"forget (all )?(previous|above|prior)", re.I), "instruction override"),
    (re.compile(r"system\s*:", re.I), "system prompt injection"),
    (re.compile(r"SYSTEM PROMPT", re.I), "system prompt injection"),
    (re.compile(r"<hidden>|<!--.*?-->", re.I | re.S), "hidden content"),
    (re.compile(r"\[INST\]|\[/INST\]", re.I), "instruction tag injection"),
    (re.compile(r"<\|im_start\|>|<\|im_end\|>", re.I), "chat template injection"),
    (re.compile(r"jailbreak", re.I), "restriction bypass"),
    (re.compile(r"bypass (all )?(safety|security|filter|restriction)", re.I), "restriction bypass"),
    (re.compile(r"override (all )?(safety|security|instruction)", re.I), "restriction bypass"),
    (re.compile(r"act as (?:an? )?(?:un(?:filtered|censored)|evil)", re.I), "role hijack"),
]

_INVISIBLE_CODEPOINTS = frozenset({
    "\u200d",  # Zero-Width Joiner
    "\u200c",  # Zero-Width Non-Joiner
    "\ufeff",  # Byte Order Mark
    "\u200e",  # Left-to-Right Mark
    "\u200f",  # Right-to-Left Mark
})


def scan_memory_content(content: str) -> str | None:
    """Scan content for injection patterns.

    Returns an error description if unsafe content is detected, or None
    if the content is clean.
    """
    for char in content:
        if char in _INVISIBLE_CODEPOINTS:
            return f"invisible unicode character detected (U+{ord(char):04X})"

    for pattern, category in _INJECTION_PATTERNS:
        if pattern.search(content):
            return f"prompt injection pattern detected: {category}"

    return None
