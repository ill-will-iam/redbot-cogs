"""Dependency-free trigger normalization and whole-word/phrase matching."""
import re
from typing import Dict, List, Optional, Pattern, Tuple

MAX_TRIGGER_LENGTH = 60
MAX_RESPONSE_LENGTH = 1000
MAX_RULES = 150
TRIGGER_FORMAT = re.compile(
    r"[^\W_]+(?:['’\-][^\W_]+)*(?:\s+[^\W_]+(?:['’\-][^\W_]+)*){0,4}\Z",
    re.UNICODE,
)


def normalize_trigger(trigger: str) -> str:
    return " ".join(trigger.strip().casefold().split())


def valid_trigger(trigger: str) -> bool:
    norm = normalize_trigger(trigger)
    return bool(1 <= len(norm) <= MAX_TRIGGER_LENGTH and TRIGGER_FORMAT.fullmatch(norm))


def compile_rules(rules: Dict[str, str]) -> List[Tuple[str, Pattern[str]]]:
    """Longest trigger first so a message receives at most one response."""
    compiled = []
    for trigger in sorted(rules, key=lambda v: (-len(v), v)):
        expr = re.escape(trigger).replace(r"\ ", r"\s+")
        compiled.append((trigger, re.compile(r"(?<!\w)(?:" + expr + r")(?!\w)")))
    return compiled


def find_response(content: str, compiled: List[Tuple[str, Pattern[str]]]) -> Optional[str]:
    """Match whole words or phrases, case-insensitively."""
    folded = content.casefold()
    for trigger, pattern in compiled:
        if pattern.search(folded):
            return trigger
    return None


def parse_rule_input(raw: str) -> Tuple[str, str]:
    """Parse trigger | response, preserving any later pipes in the response."""
    if "|" not in raw:
        raise ValueError("Separate the trigger and reply with a `|` character.")
    trigger, response = raw.split("|", 1)
    trigger = normalize_trigger(trigger)
    response = response.strip()
    if not valid_trigger(trigger):
        raise ValueError("Trigger must be 1–60 characters, up to five words (letters/numbers/apostrophes/hyphens).")
    if not response or len(response) > MAX_RESPONSE_LENGTH:
        raise ValueError("Response must be 1–1000 characters.")
    return trigger, response
