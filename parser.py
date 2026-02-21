"""Detect commitments in text and extract tasks, durations, conditions."""
import re
from dataclasses import dataclass
from typing import Optional
from datetime import date


@dataclass
class Commitment:
    kind: str  # reminder, schedule, counter, streak, punishment
    raw_text: str
    task_description: str = ""
    duration_days: Optional[int] = None
    duration_until: Optional[str] = None  # free-form or date-like
    condition_text: Optional[str] = None
    counter_name: Optional[str] = None
    counter_target: Optional[int] = None
    punishment_action: Optional[str] = None
    confidence: float = 0.9  # 0–1, used for review queue


# (pattern, kind, extract_fn, confidence)
PATTERNS = [
    # "I will [task] (for N days | until X)"
    (re.compile(
        r"\bI\s+will\s+([^.?!]+?)(?:\s+for\s+(\d+)\s+days?)?(?:\s+until\s+([^.?!]+))?[.?!]?$",
        re.I,
    ), "reminder", 0.95, lambda m: {
        "task_description": m.group(1).strip(),
        "duration_days": int(m.group(2)) if m.group(2) else None,
        "duration_until": m.group(3).strip() if m.group(3) else None,
    }),
    # "Day N rule: ..." or "Day N: ..."
    (re.compile(
        r"\bDay\s+(\d+)\s*(?:rule\s*)?[:\-]\s*([^\n]+)",
        re.I,
    ), "schedule", 0.95, lambda m: {
        "task_description": m.group(2).strip(),
        "counter_name": "Day",
        "counter_target": int(m.group(1)),
    }),
    # "Poll winner = N days locked" / "= 7 days locked"
    (re.compile(
        r"(?:Poll\s+winner\s*)?=\s*(\d+)\s+days?\s+(locked|denied|edging|etc\.?)",
        re.I,
    ), "counter", 0.9, lambda m: {
        "task_description": f"{m.group(2)} for poll winner",
        "duration_days": int(m.group(1)),
        "counter_name": "days_locked",
        "counter_target": int(m.group(1)),
    }),
    # "N days [task]" e.g. "7 days locked", "30 days denial"
    (re.compile(
        r"\b(\d+)\s+days?\s+(locked|denial|denied|edging|no\s+orgasm|task)",
        re.I,
    ), "counter", 0.75, lambda m: {
        "task_description": f"{m.group(2)}",
        "duration_days": int(m.group(1)),
        "counter_name": "days",
        "counter_target": int(m.group(1)),
    }),
    # "Streak: N days" or "Current streak: N"
    (re.compile(
        r"(?:current\s+)?streak\s*[:\-]\s*(\d+)\s+days?",
        re.I,
    ), "streak", 0.9, lambda m: {
        "task_description": "Maintain streak",
        "counter_target": int(m.group(1)),
    }),
    # "If [condition], then [punishment]"
    (re.compile(
        r"\bIf\s+([^,]+),\s*then\s+([^.?!]+)[.?!]?",
        re.I,
    ), "punishment", 0.95, lambda m: {
        "condition_text": m.group(1).strip(),
        "punishment_action": m.group(2).strip(),
    }),
    # "Rule: [task] (every day | daily)"
    (re.compile(
        r"\bRule\s*[:\-]\s*([^.?!]+?)(?:\s+every\s+day|\s+daily)[.?!]?$",
        re.I,
    ), "schedule", 0.9, lambda m: {
        "task_description": m.group(1).strip(),
    }),
    # "[Task] every day" at end of sentence
    (re.compile(
        r"([^.?!]+?)\s+every\s+day[.?!]?$",
        re.I,
    ), "reminder", 0.7, lambda m: {
        "task_description": m.group(1).strip(),
    }),
    # "Daily: [task]"
    (re.compile(
        r"Daily\s*[:\-]\s*([^\n]+)",
        re.I,
    ), "schedule", 0.95, lambda m: {
        "task_description": m.group(1).strip(),
    }),
    # "Ritual: ..." / "Rituals: ..."
    (re.compile(
        r"Rituals?\s*[:\-]\s*([^\n]+)",
        re.I,
    ), "schedule", 0.9, lambda m: {
        "task_description": m.group(1).strip(),
    }),
    # "Rule: ..." (standalone, any rule)
    (re.compile(
        r"Rule\s*[:\-]\s*([^\n.]+?)(?:\.|$)",
        re.I,
    ), "schedule", 0.85, lambda m: {
        "task_description": m.group(1).strip(),
    }),
    # "Must [task]" / "I must [task]"
    (re.compile(
        r"\b(?:I\s+)?must\s+([^.?!\n]+?)[.?!]?$",
        re.I,
    ), "reminder", 0.8, lambda m: {
        "task_description": m.group(1).strip(),
    }),
    # "Task: ..." / "Tasks: ..."
    (re.compile(
        r"Tasks?\s*[:\-]\s*([^\n]+)",
        re.I,
    ), "schedule", 0.9, lambda m: {
        "task_description": m.group(1).strip(),
    }),
    # "Commitment: ..."
    (re.compile(
        r"Commitment\s*[:\-]\s*([^\n]+)",
        re.I,
    ), "reminder", 0.9, lambda m: {
        "task_description": m.group(1).strip(),
    }),
]

# Time-bound event names that we skip when they're in the past (avoid last year's Locktober etc.)
PAST_EVENT_PATTERNS = [
    (re.compile(r"\bLocktober\b", re.I), 10),   # October
    (re.compile(r"\bNo\s*Nut\s*November\b", re.I), 11),
    (re.compile(r"\bNNN\b", re.I), 11),
    (re.compile(r"\bDenial\s*December\b", re.I), 12),
]


def _is_past_time_bound_event(raw_text: str) -> bool:
    """True if text is about a time-bound event (e.g. Locktober) and we're not in that month now."""
    now = date.today()
    for pattern, event_month in PAST_EVENT_PATTERNS:
        if pattern.search(raw_text) and now.month != event_month:
            return True
    return False


def is_past_time_bound_event(raw_text: str) -> bool:
    """Public helper: True if this commitment should be hidden (past time-bound event)."""
    if not raw_text or not isinstance(raw_text, str):
        return False
    return _is_past_time_bound_event(raw_text.strip())


def extract_commitments(text: str) -> list[Commitment]:
    """Parse a block of text (e.g. post body) and return list of Commitment objects."""
    if not text or not text.strip():
        return []
    commitments = []
    # Normalize: split on newlines and sentence endings so we don't miss rules in lists
    lines = re.split(r"[\n.;]+", text)
    seen_raw = set()
    for line in lines:
        line = line.strip()
        if len(line) < 5:
            continue
        for pattern, kind, confidence, extract in PATTERNS:
            m = pattern.search(line)
            if not m:
                continue
            raw = line.strip()
            if raw in seen_raw:
                continue
            if _is_past_time_bound_event(raw):
                continue
            seen_raw.add(raw)
            try:
                kwargs = extract(m)
            except (IndexError, AttributeError):
                continue
            allowed = {"task_description", "duration_days", "duration_until", "condition_text",
                       "counter_name", "counter_target", "punishment_action"}
            c = Commitment(kind=kind, raw_text=raw, confidence=confidence, **{k: v for k, v in kwargs.items() if k in allowed})
            commitments.append(c)
    return commitments


def commitments_from_post_body(body: str, source_post_id: str = "") -> list[tuple[Commitment, str]]:
    """Return (Commitment, source_post_id) for each commitment found."""
    return [(c, source_post_id) for c in extract_commitments(body)]
