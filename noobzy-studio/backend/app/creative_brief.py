"""Creative Brief interface (spec 8C): turns short natural-language intents
into typed, editable plan-change proposals with recorded provenance.

This is intentionally a small deterministic keyword/phrase matcher, not a
claim of full language understanding -- every parse is traceable to the
rule that fired, and anything unmatched is returned as `unrecognized` for
manual handling rather than silently guessed at.
"""
from __future__ import annotations

import re

_RULES: list[tuple[re.Pattern, callable]] = [
    (re.compile(r"more suspense|more tension", re.I),
     lambda m: {"action": "increase_anticipation", "target": "reveal_beats", "param": "anticipation_ms", "delta": 150}),
    (re.compile(r"softer zoom|less zoom|gentler zoom", re.I),
     lambda m: {"action": "adjust_param", "target": "motion.zoom", "param": "zoom_amount", "multiplier": 0.5}),
    (re.compile(r"(fewer|less|three less|reduce).*(meme|sfx|sound effect)", re.I),
     lambda m: {"action": "adjust_density", "target": "sound_cue_plan", "param": "density", "value": "light"}),
    (re.compile(r"high.?energy|more sfx|busier", re.I),
     lambda m: {"action": "adjust_density", "target": "sound_cue_plan", "param": "density", "value": "high-energy"}),
    (re.compile(r"keep.*talking|never stop narrat|always talking", re.I),
     lambda m: {"action": "increase_coverage", "target": "narration", "param": "target_coverage", "value": 0.95}),
    (re.compile(r"make (this|it) a short|turn.*into a short", re.I),
     lambda m: {"action": "change_preset", "value": "SHORT_EGG_REVEAL"}),
    (re.compile(r"full subtitles|word.for.word subtitles", re.I),
     lambda m: {"action": "set_caption_mode", "value": "full"}),
    (re.compile(r"selective captions|key word(s)? only", re.I),
     lambda m: {"action": "set_caption_mode", "value": "selective"}),
    (re.compile(r"learn (this|the) style|learn from (this|my) (video|tutorial)", re.I),
     lambda m: {"action": "trigger_skill", "skill_id": "noobzy-teach-from-video"}),
]


def parse_intent(text: str) -> dict:
    for pattern, builder in _RULES:
        m = pattern.search(text)
        if m:
            action = builder(m)
            action["matched_rule"] = pattern.pattern
            return action
    return {"action": "unrecognized", "note": "No matching rule; needs manual review.", "raw_text": text}
