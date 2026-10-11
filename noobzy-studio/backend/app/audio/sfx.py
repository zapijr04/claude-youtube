"""Procedural SFX synthesis -- NumPy, no network, no license needed.

Every function here renders a short WAV file entirely from generated
waveforms (sine/sweep/noise envelopes). Nothing is downloaded or copied
from a reference video. All assets get safe fade-in/out and peak
normalization so none of them clip or sound like raw noise.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

SR = 48000


def _fade(samples: np.ndarray, fade_in_s: float = 0.003, fade_out_s: float = 0.02) -> np.ndarray:
    n = len(samples)
    fi = min(int(fade_in_s * SR), n // 2)
    fo = min(int(fade_out_s * SR), n // 2)
    if fi > 0:
        samples[:fi] *= np.linspace(0, 1, fi)
    if fo > 0:
        samples[-fo:] *= np.linspace(1, 0, fo)
    return samples


def _normalize(samples: np.ndarray, peak: float = 0.85) -> np.ndarray:
    m = np.max(np.abs(samples)) if len(samples) else 0.0
    if m > 1e-9:
        samples = samples * (peak / m)
    return samples


def _write_wav(path: Path, samples: np.ndarray) -> None:
    import wave
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.clip(samples, -1.0, 1.0)
    pcm16 = (pcm * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm16.tobytes())


def _t(duration_s: float) -> np.ndarray:
    return np.linspace(0, duration_s, int(SR * duration_s), endpoint=False)


def click(duration_s: float = 0.03, freq: float = 1800.0) -> np.ndarray:
    t = _t(duration_s)
    env = np.exp(-t * 90)
    return _normalize(_fade(np.sin(2 * np.pi * freq * t) * env, 0.0005, 0.02))


def pop(duration_s: float = 0.08, freq: float = 650.0) -> np.ndarray:
    t = _t(duration_s)
    env = np.exp(-t * 35)
    sweep = freq * (1 + 2 * np.exp(-t * 40))
    return _normalize(_fade(np.sin(2 * np.pi * sweep * t) * env, 0.001, 0.03))


def whoosh(duration_s: float = 0.35, rising: bool = True) -> np.ndarray:
    t = _t(duration_s)
    rng = np.random.default_rng(42)
    noise = rng.standard_normal(len(t))
    freq = np.linspace(200, 2200, len(t)) if rising else np.linspace(2200, 200, len(t))
    carrier = np.sin(2 * np.pi * np.cumsum(freq) / SR)
    env = np.hanning(len(t))
    sig = (0.6 * carrier + 0.4 * noise) * env
    return _normalize(_fade(sig, 0.01, 0.05))


def sub_bass_hit(duration_s: float = 0.4) -> np.ndarray:
    t = _t(duration_s)
    freq = 110 * np.exp(-t * 8)
    env = np.exp(-t * 7)
    return _normalize(_fade(np.sin(2 * np.pi * freq * t) * env, 0.001, 0.08))


def countdown_bleep(duration_s: float = 0.12, freq: float = 880.0) -> np.ndarray:
    t = _t(duration_s)
    env = np.ones_like(t)
    env[-int(0.02 * SR):] = np.linspace(1, 0, int(0.02 * SR))
    return _normalize(np.sin(2 * np.pi * freq * t) * env)


def error_beep(duration_s: float = 0.25, freq: float = 180.0) -> np.ndarray:
    t = _t(duration_s)
    sig = np.sign(np.sin(2 * np.pi * freq * t)) * 0.5  # harsh square-ish buzz
    return _normalize(_fade(sig, 0.002, 0.03))


def coin_chime(duration_s: float = 0.3) -> np.ndarray:
    t = _t(duration_s)
    sig = (
        np.sin(2 * np.pi * 988 * t) * np.exp(-t * 6)
        + np.sin(2 * np.pi * 1318 * t) * np.exp(-t * 5) * 0.7
    )
    return _normalize(_fade(sig, 0.001, 0.08))


def ticking(duration_s: float = 0.05, freq: float = 3000.0) -> np.ndarray:
    t = _t(duration_s)
    env = np.exp(-t * 150)
    return _normalize(_fade(np.sin(2 * np.pi * freq * t) * env, 0.0005, 0.01))


def rising_tension_tone(duration_s: float = 1.2) -> np.ndarray:
    t = _t(duration_s)
    freq = np.linspace(220, 660, len(t))
    env = np.linspace(0.05, 0.8, len(t))
    return _normalize(_fade(np.sin(2 * np.pi * np.cumsum(freq) / SR) * env, 0.05, 0.02))


def digital_glitch(duration_s: float = 0.2) -> np.ndarray:
    rng = np.random.default_rng(7)
    t = _t(duration_s)
    base = np.sin(2 * np.pi * 400 * t)
    chunks = (rng.random(len(t)) > 0.7).astype(float)
    return _normalize(_fade(base * chunks, 0.001, 0.02))


def reward_jingle(duration_s: float = 0.6) -> np.ndarray:
    t = _t(duration_s)
    notes = [523, 659, 784, 1046]
    seg = len(t) // len(notes)
    sig = np.zeros_like(t)
    for i, f in enumerate(notes):
        s, e = i * seg, (i + 1) * seg if i < len(notes) - 1 else len(t)
        tt = t[s:e] - t[s]
        sig[s:e] = np.sin(2 * np.pi * f * tt) * np.exp(-tt * 4)
    return _normalize(_fade(sig, 0.001, 0.08))


# name -> generator, (category hint kept in sfx_library.py)
GENERATORS = {
    "click_soft": lambda: click(0.025, 1400),
    "click_hard": lambda: click(0.04, 2400),
    "pop": pop,
    "whoosh_rise": lambda: whoosh(0.35, True),
    "whoosh_fall": lambda: whoosh(0.3, False),
    "sub_bass_hit": sub_bass_hit,
    "countdown_bleep": countdown_bleep,
    "error_beep": error_beep,
    "coin_chime": coin_chime,
    "ticking": ticking,
    "rising_tension": rising_tension_tone,
    "digital_glitch": digital_glitch,
    "reward_jingle": reward_jingle,
}


def render_all(out_dir: str | Path) -> dict[str, str]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, gen in GENERATORS.items():
        samples = gen()
        path = out_dir / f"{name}.wav"
        _write_wav(path, samples)
        paths[name] = str(path)
    return paths
