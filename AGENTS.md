# AGENTS.md

## Purpose

This repo is a parametric OpenSCAD model for a Mac Studio under-desk enclosure
designed around Secretlab Magnus Pro mounting geometry.

- `mac_studio_enclosure.scad` is the source of truth for enclosure geometry.
- `turnaround.py` is for visualization and review only; it does not generate the
  enclosure model.

## Coordinate / Orientation Notes

- The OpenSCAD model is exported in print orientation.
- `turnaround.py` rotates the enclosure out of print orientation for display and
  review renders.
- The Mac Studio USDZ import in `turnaround.py` is intentionally locked to an
  explicit orientation so asymmetric enclosure features stay on the intended
  rendered side.
- Do not reintroduce bounding-box "best fit" rotation logic for the Mac Studio
  asset; the square footprint makes that ambiguous and can confuse left/right
  validation.
- When evaluating front access or left/right asymmetry in renders, trust the
  current deterministic orientation path in `turnaround.py`.
