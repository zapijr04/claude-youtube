"""Typed data contracts for NOOBZY AI STUDIO.

These are the canonical Pydantic models referenced by section 9 of the build
spec. The TimelineDocument is the single source of truth every render/export
derives from.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class AspectPreset(str, Enum):
    LONG_FORM_STORY = "LONG_FORM_STORY"  # 16:9
    SHORT_EGG_REVEAL = "SHORT_EGG_REVEAL"  # 9:16


class ProjectStatus(str, Enum):
    draft = "draft"
    analyzing = "analyzing"
    ready = "ready"
    rendering = "rendering"
    rendered = "rendered"
    failed = "failed"


class Project(BaseModel):
    id: str = Field(default_factory=lambda: new_id("proj"))
    name: str
    preset: AspectPreset
    status: ProjectStatus = ProjectStatus.draft
    target_duration_sec: float = 420.0  # 7 min default long-form
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    notes: str = ""


class SourceMedia(BaseModel):
    id: str = Field(default_factory=lambda: new_id("media"))
    project_id: str
    path: str
    is_simulated_fixture: bool = False
    codec: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    duration_sec: Optional[float] = None
    has_audio: bool = False
    proxy_path: Optional[str] = None
    waveform_path: Optional[str] = None
    thumbnails: list[str] = Field(default_factory=list)
    imported_at: datetime = Field(default_factory=datetime.utcnow)


class EvidenceKind(str, Enum):
    scene_cut_detected = "scene_cut_detected"
    manual_marker = "manual_marker"
    simulated_annotation = "simulated_annotation"
    vad_speech = "vad_speech"
    user_override = "user_override"


class AnalyzedEvent(BaseModel):
    """A grounded observation about the source media, never fabricated."""

    id: str = Field(default_factory=lambda: new_id("evt"))
    media_id: str
    source_timestamp_sec: float
    label: str
    evidence_kind: EvidenceKind
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    detail: str = ""


class Scene(BaseModel):
    id: str = Field(default_factory=lambda: new_id("scene"))
    media_id: str
    source_in_sec: float
    source_out_sec: float
    evidence_kind: EvidenceKind
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    keep: bool = True
    reason: str = ""
    playback_rate: float = Field(default=1.0, gt=0.0)
    """>1.0 = sped up (speed ramp), <1.0 = slow motion. Output duration of
    this scene becomes (source_out_sec - source_in_sec) / playback_rate.
    Changing this requires retiming every downstream beat/narration/graphic/
    motion/sound-cue timestamp -- see app.timeline.retime.apply_speed_ramp."""


class StoryBeatKind(str, Enum):
    hook = "hook"
    goal = "goal"
    attempt = "attempt"
    complication = "complication"
    strategy = "strategy"
    setback = "setback"
    climax = "climax"
    outcome = "outcome"
    mini_hook = "mini_hook"


class StoryBeat(BaseModel):
    id: str = Field(default_factory=lambda: new_id("beat"))
    kind: StoryBeatKind
    output_start_sec: float
    output_end_sec: float
    source_scene_ids: list[str] = Field(default_factory=list)
    summary: str = ""


class SpeechAlignment(BaseModel):
    """Word/char timing for one narration block, from a TTS provider or estimate."""

    word: str
    start_ms: int
    end_ms: int
    estimated: bool = False


class NarrationProvider(str, Enum):
    elevenlabs = "elevenlabs"
    local_fallback = "local_fallback"


class NarrationBlock(BaseModel):
    id: str = Field(default_factory=lambda: new_id("vo"))
    story_beat_id: Optional[str] = None
    text: str
    provider: NarrationProvider = NarrationProvider.local_fallback
    voice_id: Optional[str] = None
    audio_path: Optional[str] = None
    output_start_sec: float = 0.0
    duration_sec: float = 0.0
    alignment: list[SpeechAlignment] = Field(default_factory=list)
    grounded_in_timestamps: list[float] = Field(default_factory=list)
    is_placeholder_voice: bool = True


class GraphicLayerKind(str, Enum):
    kinetic_caption = "kinetic_caption"
    timer = "timer"
    counter = "counter"
    cutout_overlay = "cutout_overlay"
    comparison_card = "comparison_card"
    end_screen = "end_screen"
    hero_card = "hero_card"
    arrow = "arrow"


class GraphicLayer(BaseModel):
    id: str = Field(default_factory=lambda: new_id("gfx"))
    kind: GraphicLayerKind
    output_start_sec: float
    output_end_sec: float
    params: dict[str, Any] = Field(default_factory=dict)


class MotionPresetKind(str, Enum):
    zoom = "zoom"
    pan = "pan"
    shake = "shake"
    speed_ramp = "speed_ramp"
    parallax_2_5d = "parallax_2_5d"


class MotionPreset(BaseModel):
    id: str = Field(default_factory=lambda: new_id("motion"))
    kind: MotionPresetKind
    output_start_sec: float
    output_end_sec: float
    params: dict[str, Any] = Field(default_factory=dict)


class AudioTrackKind(str, Enum):
    voice = "voice"
    sfx = "sfx"
    game_audio = "game_audio"
    music = "music"
    ambience = "ambience"


class AudioTrack(BaseModel):
    id: str = Field(default_factory=lambda: new_id("track"))
    kind: AudioTrackKind
    gain_db: float = 0.0
    muted: bool = False
    solo: bool = False


# ---- Audio / SFX subsystem (section 8A) ----


class SoundCueCategory(str, Enum):
    EGG_OPEN = "EGG_OPEN"
    STEAL_SUCCESS = "STEAL_SUCCESS"
    STEAL_FAILED = "STEAL_FAILED"
    CHASE = "CHASE"
    SUDDEN_ZOOM = "SUDDEN_ZOOM"
    TEXT_POP = "TEXT_POP"
    ARROW_APPEAR = "ARROW_APPEAR"
    CIRCLE_HIGHLIGHT = "CIRCLE_HIGHLIGHT"
    COUNTER_INCREMENT = "COUNTER_INCREMENT"
    TIMER_10_SECONDS = "TIMER_10_SECONDS"
    BIG_REVEAL = "BIG_REVEAL"
    FUNNY_FAIL = "FUNNY_FAIL"
    TRANSITION = "TRANSITION"
    MONEY_GAIN = "MONEY_GAIN"
    NEW_UPGRADE = "NEW_UPGRADE"
    NEAR_MISS = "NEAR_MISS"
    FINAL_PAYOFF = "FINAL_PAYOFF"
    CLIFFHANGER = "CLIFFHANGER"


class AudioAssetLicense(str, Enum):
    procedurally_generated = "procedurally_generated"  # synthesized locally, no license needed
    cc0 = "cc0"
    user_owned = "user_owned"
    unknown_not_bundled = "unknown_not_bundled"


class AudioAsset(BaseModel):
    id: str = Field(default_factory=lambda: new_id("asset"))
    name: str
    category: Optional[SoundCueCategory] = None
    file_path: str
    duration_sec: float
    license: AudioAssetLicense
    source: str = "noobzy-procedural-synth"
    attribution_required: bool = False
    tags: list[str] = Field(default_factory=list)


class SoundCue(BaseModel):
    id: str = Field(default_factory=lambda: new_id("cue"))
    audio_asset_id: str
    category: SoundCueCategory
    output_start_ms: int
    duration_ms: int
    intensity: float = Field(ge=0.0, le=1.0, default=0.7)
    gain_db: float = 0.0
    pan: float = Field(ge=-1.0, le=1.0, default=0.0)
    pitch_semitones: float = 0.0
    speed: float = 1.0
    fade_in_ms: int = 5
    fade_out_ms: int = 40
    trigger_source: EvidenceKind = EvidenceKind.manual_marker
    source_timestamp_sec: Optional[float] = None
    evidence: str = ""
    confidence: float = Field(ge=0.0, le=1.0, default=0.6)
    sync_point: Optional[str] = None
    approved: bool = True
    muted: bool = False


class SoundCuePlan(BaseModel):
    id: str = Field(default_factory=lambda: new_id("cueplan"))
    project_id: str
    density: str = "balanced"  # light|balanced|high-energy
    max_effects_per_minute: int = 20
    category_cooldown_ms: dict[str, int] = Field(default_factory=dict)
    cues: list[SoundCue] = Field(default_factory=list)


class MixBus(BaseModel):
    id: str = Field(default_factory=lambda: new_id("bus"))
    kind: AudioTrackKind
    gain_db: float = 0.0
    duck_target_db: Optional[float] = None  # applied when voice bus is active


class MixAutomation(BaseModel):
    bus_id: str
    at_sec: float
    gain_db: float


class BeatMarker(BaseModel):
    at_sec: float
    strength: float = Field(ge=0.0, le=1.0, default=0.5)


class RenderQualityReport(BaseModel):
    id: str = Field(default_factory=lambda: new_id("qc"))
    export_job_id: str
    integrated_lufs: Optional[float] = None
    true_peak_dbtp: Optional[float] = None
    clipping_detected: bool = False
    voice_coverage_ratio: Optional[float] = None
    silent_gaps_over_threshold: list[dict[str, float]] = Field(default_factory=list)
    sfx_cues_verified_audible: int = 0
    notes: list[str] = Field(default_factory=list)


class CreativeFeedbackRecord(BaseModel):
    id: str = Field(default_factory=lambda: new_id("fb"))
    project_id: Optional[str] = None
    intent_text: str
    parsed_action: dict[str, Any] = Field(default_factory=dict)
    accepted: Optional[bool] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CreativeStyleProfile(BaseModel):
    id: str = Field(default_factory=lambda: new_id("style"))
    name: str
    source: str  # "manual" | "reference_video:<media_id>" | "built_in"
    recipe: dict[str, Any] = Field(default_factory=dict)
    confidence_notes: str = ""
    needs_manual_recipe: bool = False


class EffectPreset(BaseModel):
    id: str = Field(default_factory=lambda: new_id("preset"))
    name: str
    kind: str
    params: dict[str, Any] = Field(default_factory=dict)


# ---- Timeline document: the source of truth ----


class TimelineDocument(BaseModel):
    schema_version: str = "1.0.0"
    id: str = Field(default_factory=lambda: new_id("tl"))
    project_id: str
    preset: AspectPreset
    width: int
    height: int
    fps: float
    total_duration_sec: float
    scenes: list[Scene] = Field(default_factory=list)
    beats: list[StoryBeat] = Field(default_factory=list)
    narration: list[NarrationBlock] = Field(default_factory=list)
    graphics: list[GraphicLayer] = Field(default_factory=list)
    motion: list[MotionPreset] = Field(default_factory=list)
    audio_tracks: list[AudioTrack] = Field(default_factory=list)
    sound_cue_plan: Optional[SoundCuePlan] = None
    target_lufs: float = -14.0
    """Persisted project-level mastering target -- part of the editable,
    autosaved project state, not a one-off render parameter."""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ---- Skills / memory / compute / export ----


class SkillManifest(BaseModel):
    id: str  # stable slug, e.g. "noobzy-hook"
    version: str = "1.0.0"
    title: str
    description: str
    triggers: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    allowed_parameters: dict[str, Any] = Field(default_factory=dict)
    examples: list[str] = Field(default_factory=list)
    provenance: str = "built_in"
    enabled: bool = True
    skill_md_path: Optional[str] = None


class MemoryRecordKind(str, Enum):
    channel_profile = "channel_profile"
    creator_preference = "creator_preference"
    editing_rule = "editing_rule"
    approved_skill = "approved_skill"
    reference_style_analysis = "reference_style_analysis"
    scene_note = "scene_note"
    production_feedback = "production_feedback"
    analytics_import = "analytics_import"


class MemoryRecord(BaseModel):
    id: str = Field(default_factory=lambda: new_id("mem"))
    kind: MemoryRecordKind
    key: str
    value: dict[str, Any] = Field(default_factory=dict)
    version: int = 1
    provenance: str = "user"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ComputeProviderKind(str, Enum):
    local_cpu = "local_cpu"
    local_gpu = "local_gpu"
    comfyui_local = "comfyui_local"
    runpod_gpu = "runpod_gpu"


class ComputeJobStatus(str, Enum):
    not_configured = "not_configured"
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"
    awaiting_cost_approval = "awaiting_cost_approval"


class ComputeJob(BaseModel):
    id: str = Field(default_factory=lambda: new_id("job"))
    provider: ComputeProviderKind
    status: ComputeJobStatus = ComputeJobStatus.not_configured
    model: Optional[str] = None
    required_gpu_capability: Optional[str] = None
    estimated_cost_usd: Optional[float] = None
    max_cost_usd: Optional[float] = None
    log: list[str] = Field(default_factory=list)


class CostApproval(BaseModel):
    id: str = Field(default_factory=lambda: new_id("approval"))
    compute_job_id: str
    max_spend_usd: float
    approved_by_user: bool = False
    approved_at: Optional[datetime] = None


class ExportJobKind(str, Enum):
    mp4 = "mp4"
    srt = "srt"
    stems = "stems"
    timeline_json = "timeline_json"
    otio = "otio"
    fcpxml = "fcpxml"


class ExportJob(BaseModel):
    id: str = Field(default_factory=lambda: new_id("export"))
    project_id: str
    kind: ExportJobKind
    status: str = "pending"
    output_path: Optional[str] = None
    error: Optional[str] = None
