"""Sound-cue style presets and placement rules (spec section 8A/A2).

Each category maps to one or more named presets. A preset is a short
sequence of (asset_name, offset_ms_from_sync_point, gain_db) components --
e.g. BIG_REVEAL = a riser starting 400ms before the reveal frame, then an
impact chime exactly at it. assign_assets() expands the planner's
one-cue-per-event output into concrete, asset-backed SoundCue entries,
enforcing a per-category cooldown and a max-cues-per-minute cap so nothing
is spammed.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.schemas import SoundCue, SoundCueCategory, SoundCuePlan

Component = tuple[str, int, float]  # (asset_name, offset_ms, gain_db)


@dataclass
class Preset:
    name: str
    category: SoundCueCategory
    components: list[Component]


# >= 25 named presets across the 18 trigger categories, per spec A2.
PRESETS: list[Preset] = [
    Preset("egg_open_quick_pop", SoundCueCategory.EGG_OPEN, [("click_soft", -250, -2), ("pop", 0, 0)]),
    Preset("egg_open_rare_crack", SoundCueCategory.EGG_OPEN, [("click_hard", -300, 0), ("coin_chime", 50, -1)]),
    Preset("steal_success_snatch", SoundCueCategory.STEAL_SUCCESS, [("whoosh_rise", -120, -1), ("countdown_bleep", 0, -3)]),
    Preset("steal_success_reward", SoundCueCategory.STEAL_SUCCESS, [("coin_chime", 0, -1)]),
    Preset("steal_failed_scratch", SoundCueCategory.STEAL_FAILED, [("error_beep", 0, -2)]),
    Preset("steal_failed_thunk", SoundCueCategory.STEAL_FAILED, [("sub_bass_hit", 0, -1), ("click_hard", 60, -4)]),
    Preset("chase_tick_loop", SoundCueCategory.CHASE, [("ticking", 0, -6)]),
    Preset("chase_whoosh_speed", SoundCueCategory.CHASE, [("whoosh_rise", 0, -3)]),
    Preset("sudden_zoom_whoosh", SoundCueCategory.SUDDEN_ZOOM, [("whoosh_rise", 0, -2)]),
    Preset("sudden_zoom_punch", SoundCueCategory.SUDDEN_ZOOM, [("whoosh_fall", 0, -2), ("click_hard", 0, -4)]),
    Preset("text_pop_soft", SoundCueCategory.TEXT_POP, [("click_soft", 0, -4)]),
    Preset("arrow_appear_tick", SoundCueCategory.ARROW_APPEAR, [("click_soft", 0, -5)]),
    Preset("circle_highlight_blip", SoundCueCategory.CIRCLE_HIGHLIGHT, [("countdown_bleep", 0, -6)]),
    Preset("counter_increment_tick", SoundCueCategory.COUNTER_INCREMENT, [("ticking", 0, -4)]),
    Preset("timer_10s_bleep", SoundCueCategory.TIMER_10_SECONDS, [("countdown_bleep", 0, -3)]),
    Preset("big_reveal_riser_chime", SoundCueCategory.BIG_REVEAL, [("rising_tension", -400, -2), ("coin_chime", 0, 0)]),
    Preset("big_reveal_riser_impact", SoundCueCategory.BIG_REVEAL, [("rising_tension", -500, -3), ("sub_bass_hit", 0, -1)]),
    Preset("funny_fail_bop", SoundCueCategory.FUNNY_FAIL, [("pop", 0, -3), ("error_beep", 80, -8)]),
    Preset("transition_whoosh", SoundCueCategory.TRANSITION, [("whoosh_fall", 0, -3)]),
    Preset("transition_glitch", SoundCueCategory.TRANSITION, [("digital_glitch", 0, -4)]),
    Preset("money_gain_chime", SoundCueCategory.MONEY_GAIN, [("coin_chime", 0, -1)]),
    Preset("new_upgrade_jingle", SoundCueCategory.NEW_UPGRADE, [("reward_jingle", 0, -1)]),
    Preset("near_miss_glitch", SoundCueCategory.NEAR_MISS, [("digital_glitch", 0, -2), ("sub_bass_hit", 40, -4)]),
    Preset("final_payoff_jingle", SoundCueCategory.FINAL_PAYOFF, [("reward_jingle", -100, 0)]),
    Preset("final_payoff_big", SoundCueCategory.FINAL_PAYOFF, [("rising_tension", -600, -3), ("reward_jingle", 0, 0)]),
    Preset("cliffhanger_riser", SoundCueCategory.CLIFFHANGER, [("rising_tension", -500, -2)]),
]

PRESETS_BY_CATEGORY: dict[SoundCueCategory, list[Preset]] = {}
for _p in PRESETS:
    PRESETS_BY_CATEGORY.setdefault(_p.category, []).append(_p)

DENSITY_MAX_PER_MINUTE = {"light": 8, "balanced": 20, "high-energy": 36}
DEFAULT_COOLDOWN_MS = 1500


def assign_assets(
    plan: SoundCuePlan, asset_ids_by_name: dict[str, str], density: str = "balanced"
) -> SoundCuePlan:
    """Expand each category-level cue into concrete, asset-backed SoundCues.

    Applies a per-category cooldown and an overall max-effects-per-minute
    cap -- cues beyond the cap are dropped (muted=True) rather than piling
    up, matching the "no repeated meme SFX" requirement.
    """
    plan.density = density
    max_per_min = DENSITY_MAX_PER_MINUTE.get(density, 20)
    last_fired_ms: dict[SoundCueCategory, int] = {}
    expanded: list[SoundCue] = []
    minute_bucket: dict[int, int] = {}

    for cue in sorted(plan.cues, key=lambda c: c.output_start_ms):
        presets = PRESETS_BY_CATEGORY.get(cue.category, [])
        if not presets:
            continue
        preset = presets[0]  # deterministic default; UI can offer the others

        cooldown = plan.category_cooldown_ms.get(cue.category.value, DEFAULT_COOLDOWN_MS)
        last = last_fired_ms.get(cue.category)
        if last is not None and cue.output_start_ms - last < cooldown:
            continue

        minute = cue.output_start_ms // 60000
        if minute_bucket.get(minute, 0) >= max_per_min:
            continue

        for asset_name, offset_ms, gain_db in preset.components:
            asset_id = asset_ids_by_name.get(asset_name)
            if asset_id is None:
                continue
            start_ms = max(0, cue.output_start_ms + offset_ms)
            expanded.append(
                SoundCue(
                    audio_asset_id=asset_id,
                    category=cue.category,
                    output_start_ms=start_ms,
                    duration_ms=cue.duration_ms,
                    gain_db=gain_db,
                    trigger_source=cue.trigger_source,
                    source_timestamp_sec=cue.source_timestamp_sec,
                    evidence=cue.evidence,
                    confidence=cue.confidence,
                    sync_point=preset.name,
                )
            )
        last_fired_ms[cue.category] = cue.output_start_ms
        minute_bucket[minute] = minute_bucket.get(minute, 0) + 1

    plan.cues = expanded
    return plan
