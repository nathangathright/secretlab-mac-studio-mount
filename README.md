# Mac Studio Under-Desk Mount

A 3D-printable enclosure for mounting a Mac Studio under a [Secretlab Magnus Pro](https://secretlab.co/pages/magnus-pro) desk. The Magnus Pro has threaded screw holes on the underside of its metal tabletop, and Secretlab sells a [Premium PC Mount](https://secretlab.co/products/premium-pc-mount?sku=MAG-PCMNT-BLK) that bolts into them — but its adjustable arms bottom out at 6.7 × 14", far too large for a Mac Studio. This enclosure bridges the gap: it wraps the Mac Studio in a rigid shell with screw slots that bolt directly to the Magnus Pro's mounting points.

The design is fully parametric — all dimensions derive from the Mac Studio's own geometry, so you can adapt it to any Mac Studio model by updating a few measurements.

## Files

| File | Description |
|------|-------------|
| `mac_studio_enclosure.scad` | Parametric OpenSCAD source — the primary design file |
| `mac_studio_enclosure.stl` | Pre-built STL, ready to slice and print |
| `mac_studio_enclosure_spec.txt` | Plain-English design specification with all formulas and rationale |
| `PRINTING.md` | Print orientation, material selection, slicer settings, and post-processing |
| `turnaround.py` | Blender script to render a 360° turnaround video of the enclosure |

## Printing

**Material:** PETG recommended. Do not use PLA — the Mac Studio's exhaust heat will soften it.

**Orientation:** Print upside-down with the top face (square cutout) on the build plate. This gives the best corner finish, strongest layer orientation for mounting loads, and requires no supports.

**Bed size:** 210 mm × 210 mm minimum.

See [PRINTING.md](PRINTING.md) for full instructions.

## Customizing the Design

Open `mac_studio_enclosure.scad` in [OpenSCAD](https://openscad.org/) and edit the measurements at the top of the file. The spec file explains what each measurement controls and how the enclosure dimensions are derived.

To regenerate the STL: **Design → Render (F6)** then **File → Export → STL**.

## Mounting

The enclosure has four converging screw slots on each side face, sized for M5 bolts with 10 mm of adjustment travel. Fasten one side to the underside of your desk (or a mounting bracket). The open back faces outward for cable access.

## Turnaround Video

To render a 360° turnaround video (requires [Blender](https://www.blender.org/) and ffmpeg):

```
/Applications/Blender.app/Contents/MacOS/Blender --background --python turnaround.py
```

Output is saved to `turnaround_output/turnaround.mp4`.

## License

This project is open source. Feel free to use, modify, and share.
