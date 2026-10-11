---
{
  "id": "noobzy-qc",
  "version": "1.0.0",
  "title": "Noobzy Quality Control",
  "description": "Factual alignment, no dead air, no clipped captions, no black frames/broken links, aspect ratio and audio checks.",
  "triggers": [
    "qc",
    "quality check",
    "before export"
  ],
  "capabilities": [
    "qc.render_quality_report"
  ],
  "dependencies": [],
  "allowed_parameters": {
    "max_silent_gap_sec": 1.25
  },
  "examples": [
    "Run QC on the rendered MP4 before export."
  ],
  "provenance": "built_in"
}
---

# Noobzy Quality Control

Factual alignment, no dead air, no clipped captions, no black frames/broken links, aspect ratio and audio checks.

## Triggers
- qc
- quality check
- before export

## Capabilities
- qc.render_quality_report

## Examples
- Run QC on the rendered MP4 before export.
