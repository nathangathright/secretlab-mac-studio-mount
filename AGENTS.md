# AGENTS.md

## Purpose

This repo is a parametric OpenSCAD model for a Mac Studio under-desk enclosure
designed around Secretlab Magnus Pro mounting geometry.

- `main.py` is the source of truth for enclosure geometry, build context, and
  generated reference docs.
- `mac_studio_enclosure.scad` is a generated export of that geometry.
- `turnaround.py` is for visualization and review only; it does not generate the
  enclosure model.

## Coordinate / Orientation Notes

- The OpenSCAD model is exported in print orientation.
- `turnaround.py` rotates the enclosure out of print orientation for display and
  review renders.
