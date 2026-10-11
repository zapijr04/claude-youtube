---
{
  "id": "noobzy-audio",
  "version": "1.0.0",
  "title": "Noobzy Audio Identity",
  "description": "Clear VO, subtle copyright-safe music, dynamic ducking, game sounds and purposeful SFX, 0.3-0.7s reveal pause.",
  "triggers": [
    "audio",
    "mix",
    "sound design"
  ],
  "capabilities": [
    "audio.mix",
    "audio.duck",
    "audio.loudness_qc"
  ],
  "dependencies": [
    "noobzy-sfx-auto",
    "noobzy-audio-mix"
  ],
  "allowed_parameters": {
    "target_lufs": -14.0,
    "target_true_peak_dbtp": -1.0,
    "reveal_pause_sec": [
      0.3,
      0.7
    ]
  },
  "examples": [
    "Mix voice, SFX, game audio and music for the current project."
  ],
  "provenance": "built_in"
}
---

# Noobzy Audio Identity

Clear VO, subtle copyright-safe music, dynamic ducking, game sounds and purposeful SFX, 0.3-0.7s reveal pause.

## Triggers
- audio
- mix
- sound design

## Capabilities
- audio.mix
- audio.duck
- audio.loudness_qc

## Examples
- Mix voice, SFX, game audio and music for the current project.
