---
{
  "id": "noobzy-beat-sync",
  "version": "1.0.0",
  "title": "Noobzy Beat Sync",
  "description": "Times SFX/title animations to music beat markers within a max permissible shift; never slides a reveal early.",
  "triggers": [
    "beat sync",
    "music sync"
  ],
  "capabilities": [
    "audio.beat_detection"
  ],
  "dependencies": [],
  "allowed_parameters": {
    "max_shift_ms": 80
  },
  "examples": [
    "Nudge the impact SFX to the nearest beat marker, within 80ms."
  ],
  "provenance": "built_in"
}
---

# Noobzy Beat Sync

Times SFX/title animations to music beat markers within a max permissible shift; never slides a reveal early.

## Triggers
- beat sync
- music sync

## Capabilities
- audio.beat_detection

## Examples
- Nudge the impact SFX to the nearest beat marker, within 80ms.
