"""Narration providers: real ElevenLabs adapter (gated by API key) + an
honestly-labeled local offline fallback for when no key is configured.

The local fallback does NOT synthesize speech (no Piper/espeak available in
this environment -- checked at startup, see `local_tts_available_note`). It
renders an audible, speech-shaped amplitude envelope (formant-ish tone
bursts at syllable rate) so the rest of the pipeline (sync, ducking,
caption timing, voice-coverage QA) can be built and tested end-to-end. It
is clearly tagged `is_placeholder_voice=True` everywhere and must never be
presented as ElevenLabs output.
"""
from __future__ import annotations

import os
import re
import wave
from pathlib import Path

import numpy as np

from app.schemas import NarrationBlock, NarrationProvider, SpeechAlignment

SR = 48000
LOCAL_TTS_NOTE = (
    "No real local TTS engine (Piper/espeak-ng) is installed in this environment. "
    "The local fallback renders a speech-shaped placeholder tone, NOT real speech. "
    "Configure ELEVENLABS_API_KEY for real narration."
)


def _words(text: str) -> list[str]:
    return [w for w in re.split(r"\s+", text.strip()) if w]


def estimate_duration_sec(text: str, words_per_minute: float = 165.0) -> float:
    n = max(1, len(_words(text)))
    return round(n / words_per_minute * 60.0, 2)


def _render_placeholder_speech(text: str, duration_s: float) -> np.ndarray:
    """Formant-like amplitude-modulated tone approximating syllable rhythm."""
    words = _words(text) or ["..."]
    n_samples = int(SR * duration_s)
    t = np.linspace(0, duration_s, n_samples, endpoint=False)
    carrier = 0.5 * np.sin(2 * np.pi * 145 * t) + 0.3 * np.sin(2 * np.pi * 290 * t)

    # one amplitude "syllable" pulse per word, spread evenly
    env = np.zeros(n_samples)
    per_word = duration_s / len(words)
    rng = np.random.default_rng(abs(hash(text)) % (2**32))
    for i in range(len(words)):
        center = (i + 0.5) * per_word
        width = per_word * 0.4
        jitter = rng.uniform(0.85, 1.0)
        env += jitter * np.exp(-0.5 * ((t - center) / max(width, 0.01)) ** 2)
    env = np.clip(env, 0, 1.2)

    sig = carrier * env
    m = np.max(np.abs(sig)) if n_samples else 0.0
    if m > 1e-9:
        sig = sig * (0.75 / m)
    return sig


def _write_wav(path: Path, samples: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm16 = (np.clip(samples, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm16.tobytes())


def synthesize_local_fallback(block: NarrationBlock, out_dir: str | Path) -> NarrationBlock:
    duration = block.duration_sec or estimate_duration_sec(block.text)
    samples = _render_placeholder_speech(block.text, duration)
    out_path = Path(out_dir) / f"{block.id}.wav"
    _write_wav(out_path, samples)

    words = _words(block.text) or ["..."]
    per_word_ms = int(duration * 1000 / len(words))
    alignment = [
        SpeechAlignment(word=w, start_ms=i * per_word_ms, end_ms=(i + 1) * per_word_ms, estimated=True)
        for i, w in enumerate(words)
    ]

    block.provider = NarrationProvider.local_fallback
    block.audio_path = str(out_path)
    block.duration_sec = duration
    block.alignment = alignment
    block.is_placeholder_voice = True
    return block


class ElevenLabsNotConfigured(RuntimeError):
    pass


def synthesize_elevenlabs(block: NarrationBlock, out_dir: str | Path, voice_id: str | None = None) -> NarrationBlock:
    """Real ElevenLabs text-to-speech-with-timestamps call.

    Uses the documented `POST /v1/text-to-speech/{voice_id}/with-timestamps`
    endpoint. Requires ELEVENLABS_API_KEY (and a voice id) in the
    environment. Raises ElevenLabsNotConfigured if missing -- callers should
    fall back to synthesize_local_fallback and surface the blocker in the UI
    rather than silently faking success.
    """
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    voice = voice_id or os.environ.get("ELEVENLABS_VOICE_ID")
    if not api_key or not voice:
        raise ElevenLabsNotConfigured(
            "ELEVENLABS_API_KEY / ELEVENLABS_VOICE_ID not set. "
            "This path is implemented but genuinely unverified without live credentials."
        )

    import base64
    import json
    import urllib.request

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps"
    payload = json.dumps(
        {"text": block.text, "model_id": "eleven_turbo_v2_5", "output_format": "mp3_44100_128"}
    ).encode()
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={"xi-api-key": api_key, "Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())

    audio_bytes = base64.b64decode(data["audio_base64"])
    out_path = Path(out_dir) / f"{block.id}.mp3"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(audio_bytes)

    chars = data.get("alignment", {}).get("characters", [])
    starts = data.get("alignment", {}).get("character_start_times_seconds", [])
    ends = data.get("alignment", {}).get("character_end_times_seconds", [])
    alignment = []
    if chars and starts and ends:
        word, w_start = "", None
        for ch, s, e in zip(chars, starts, ends):
            if ch == " ":
                if word:
                    alignment.append(SpeechAlignment(word=word, start_ms=int(w_start * 1000), end_ms=int(e * 1000)))
                word, w_start = "", None
                continue
            if w_start is None:
                w_start = s
            word += ch
        if word and w_start is not None:
            alignment.append(SpeechAlignment(word=word, start_ms=int(w_start * 1000), end_ms=int(ends[-1] * 1000)))

    block.provider = NarrationProvider.elevenlabs
    block.voice_id = voice
    block.audio_path = str(out_path)
    block.alignment = alignment
    block.is_placeholder_voice = False
    if ends:
        block.duration_sec = ends[-1]
    return block
