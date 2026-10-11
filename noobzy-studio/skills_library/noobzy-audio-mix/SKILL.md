---
{
  "id": "noobzy-audio-mix",
  "version": "1.0.0",
  "title": "Noobzy Audio Mix Engine",
  "description": "Multi-bus mixing with sidechain VO/music ducking, true-peak QA, isolated stems.",
  "triggers": [
    "ducking",
    "sidechain",
    "stems"
  ],
  "capabilities": [
    "audio.sidechain_duck",
    "audio.stems_export"
  ],
  "dependencies": [],
  "allowed_parameters": {
    "duck_ratio": 8,
    "attack_ms": 20,
    "release_ms": 400
  },
  "examples": [
    "Duck music under narration and export audio stems."
  ],
  "provenance": "built_in"
}
---

# Noobzy Audio Mix Engine

Multi-bus mixing with sidechain VO/music ducking, true-peak QA, isolated stems.

## Triggers
- ducking
- sidechain
- stems

## Capabilities
- audio.sidechain_duck
- audio.stems_export

## Examples
- Duck music under narration and export audio stems.
