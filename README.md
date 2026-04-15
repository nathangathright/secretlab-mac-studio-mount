# Mac Studio Under-Desk Mount

A 3D-printable enclosure for mounting a Mac Studio under a [Secretlab Magnus Pro](https://secretlab.co/pages/magnus-pro) desk. The Magnus Pro has threaded screw holes on the underside of its metal tabletop, and Secretlab sells a [Premium PC Mount](https://secretlab.co/products/premium-pc-mount?sku=MAG-PCMNT-BLK) that bolts into them — but its adjustable arms bottom out at 6.7 × 14", far too large for a Mac Studio. This enclosure bridges the gap: it wraps the Mac Studio in a rigid shell with screw slots that bolt directly to the Magnus Pro's mounting points.

The design is fully parametric. `main.py` is the source of truth for the measured dimensions, derived formulas, CAD generation, and generated reference docs. `README.md` stays editorial, and `turnaround.py` remains a visualization/review tool only.

## Printing

**Material:** PETG recommended. Do not use PLA — the Mac Studio's exhaust heat will soften it.

**Orientation:** The Mac Studio is used on its side inside the enclosure, but the enclosure itself prints best upside-down with the top face (square cutout) on the build plate and the vent-ring face up. This gives the best corner finish, strongest layer orientation for mounting loads, and usually does not require supports.

**Bed size:** 220 mm × 220 mm minimum. The current shell footprint is about 211 mm × 211 mm.

## Workflow

Edit the measured dimensions, formulas, or print guidance in `main.py`, then regenerate the project outputs through [OpenSCAD](https://openscad.org/):

To regenerate the generated outputs:

```bash
python3 main.py
```

To also generate a reference STL with the `mac-studio.usdz` model placed inside the enclosure:

```bash
python3 main.py --with-mac-studio-assembly
```

To generate a glass USDZ assembly for Quick Look / AR-style review, with the same validated Mac Studio placement:

```bash
python3 main.py --with-mac-studio-glass-usdz
```

If you only want to refresh the generated text/CAD sources and skip the STL export:

```bash
python3 main.py --skip-stl
```

To verify that the generated files on disk are still in sync with `main.py`:

```bash
python3 main.py --check
```

### Rear Tip Relief

The rear tips of the bottom opening are intentionally softened in the outer baseplate profile. This change rounds the tips that your hands can contact when loading the Mac Studio, but it does **not** change the vent circle or the straight rear channel cutout.

That distinction matters: the slide-in path from the back is preserved because the final bottom cutout profile is still the original circle-plus-channel geometry. The rear-tip relief changes only the exterior silhouette around that opening.

## Mounting

The enclosure has four converging screw slots on each side face, sized for M5 bolts with 10 mm of adjustment travel. Each slot now includes a flush interior counterbore sized around a 9.5 mm maximum head diameter, so either the supplied M5 button-head hex socket screws or the taller Secretlab pan-head screws sit below the interior wall surface. In use, the Mac Studio sits on its side inside the enclosure. Fasten one side to the underside of your desk (or a mounting bracket). The open back faces outward for cable access.

If you want a quieter, snugger fit, add a few thin adhesive felt pads on the interior side walls. Small pads work better than long strips and let you tune the fit without changing the CAD model.

## Turnaround Video

To render a 360° turnaround video (requires [Blender](https://www.blender.org/) and ffmpeg):

```
/Applications/Blender.app/Contents/MacOS/Blender --background --python turnaround.py
```

To render the full-quality MP4 instead of the default preview render:

```
/Applications/Blender.app/Contents/MacOS/Blender --background --python turnaround.py -- --final
```

To render a single still from the same camera orbit, use `--frame`. If you omit the frame number, it defaults to frame 25.

```
/Applications/Blender.app/Contents/MacOS/Blender --background --python turnaround.py -- --frame 25
```

Default preview output is saved to `turnaround_output/turnaround_preview.mp4`.
Final output is saved to `turnaround_output/turnaround.mp4`.
Single-frame preview output is saved to `turnaround_output/turnaround_preview_frame_####.png`.

## License

This project is open source. Feel free to use, modify, and share.
