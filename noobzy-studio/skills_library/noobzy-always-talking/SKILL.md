---
{
  "id": "noobzy-always-talking",
  "version": "1.0.0",
  "title": "Noobzy Always-Talking Narration",
  "description": "Near-continuous (90-95%) energetic narration with voice-coverage audit; no pointless filler, no 5-10s dead zones.",
  "triggers": [
    "narration",
    "voiceover",
    "coverage"
  ],
  "capabilities": [
    "audio.voice_coverage_qa"
  ],
  "dependencies": [],
  "allowed_parameters": {
    "target_coverage": [
      0.9,
      0.95
    ],
    "max_silent_gap_sec": 1.25
  },
  "examples": [
    "Audit voice coverage on the current timeline and flag gaps over 1.25s."
  ],
  "provenance": "built_in"
}
---

# Noobzy Always-Talking Narration

Near-continuous (90-95%) energetic narration with voice-coverage audit; no pointless filler, no 5-10s dead zones.

## Triggers
- narration
- voiceover
- coverage

## Capabilities
- audio.voice_coverage_qa

## Examples
- Audit voice coverage on the current timeline and flag gaps over 1.25s.
