# 3D Printing Instructions — Mac Studio Under-Desk Enclosure

## Print Orientation

Print upside-down with the top face (square cutout) on the build plate and the bottom face (circular vent cutout / vent-ring face) facing up.

```
        ┌── bottom face (circle+channel) ─┐
        │                                  │
        │         ▲ build direction        │
        │         │  (100 mm)              │
        │   rounded corners run            │
        │   vertically along build axis    │
        │         │                        │
        ├─────────┴────────────────────────┤
        │   top face on bed (square cutout)│
        └──────────────────────────────────┘
              208 mm × 208 mm footprint
              100 mm tall print
```

- **Best corner finish.** The four rounded edges run along the build axis. Each layer traces a smooth arc — no stairstepping.
- **Strong bed adhesion.** The top face has a ~138 mm square cutout, leaving a ~35 mm-wide frame of contact area (~24,000 mm²). Stable foundation with no thin strips.
- **Smooth finish where it counts.** The top face (most visible when mounted) gets the smooth bed-contact surface.
- **Short print.** Only 100 mm tall.
- **Usually no supports needed.** In the recommended orientation, the vent circle and rear channel open upward, so most slicers can print the shell cleanly without support material. If your slicer preview shows sagging bridges for your machine or material, add supports only where needed.
- **Strong layer orientation.** Mounting screw loads go through the side walls in shear (the strong direction for FDM), not in layer-separating tension.
- **Requires a 210+ mm bed** in both X and Y.


## Material

**PETG — recommended.** Best overall balance of strength, heat tolerance, and printability.

| Material | Heat Deflection | Strength | Printability | Verdict |
|----------|----------------|----------|-------------|---------|
| **PETG** | ~80 °C | Good | Easy | **Recommended** |
| ASA | ~100 °C | Very good | Moderate (needs enclosure, ventilation) | Best if you have an enclosed printer |
| ABS | ~100 °C | Good | Difficult (warps badly at 208 mm footprint) | Not recommended at this size |
| PLA | ~55 °C | Adequate | Easiest | **Do not use** — Mac Studio exhaust heat will soften it over time |
| PA/Nylon | ~180 °C | Excellent | Difficult (moisture-sensitive) | Overkill, but works if you have the setup |

**Why not PLA?** The Mac Studio's exhaust can sustain 50–60 °C at the vent surface. PLA's heat deflection temperature is ~55 °C. Under sustained load (the weight of the Mac Studio pulling on a softening enclosure), PLA will creep and deform. PETG's 80 °C threshold provides a comfortable margin.

**Why not ABS?** ABS has excellent heat resistance but shrinks significantly as it cools. On a 208 mm footprint, warping is very likely unless you have an actively heated chamber. ASA is a better alternative with similar thermal properties and less warping.


## Print Settings

| Setting | Value | Rationale |
|---------|-------|-----------|
| Layer height | 0.20 mm | Good balance of speed and surface quality |
| Nozzle | 0.4 mm | Standard; 0.6 mm also works and cuts print time ~40% |
| Wall count / perimeters | 8–10 | Fills the 4 mm wall entirely with perimeters (no infill needed). At 0.45 mm line width, 9 perimeters ≈ 4.05 mm. |
| Top / bottom solid layers | 8–10 | Ensures the enclosure's top and bottom walls (4 mm thick, printed as vertical walls) are fully solid |
| Infill | 0% | Not needed — at 4 mm wall thickness, the slicer fills everything with perimeters |
| Bed adhesion | Brim, 5–8 mm | Tall print (208 mm) on a narrow base (100 mm deep). A brim prevents the base from lifting. |
| Supports | Off by default | Usually not needed in the recommended orientation; check your slicer preview before enabling them |
| Print speed | 40–60 mm/s (PETG) | Conservative speed for good layer adhesion. Outer walls at 30–40 mm/s for surface finish. |
| Nozzle temp | 230–245 °C (PETG) | Check your filament's datasheet. Higher end improves layer bonding. |
| Bed temp | 70–80 °C (PETG) | Standard for PETG adhesion |
| Cooling fan | 30–50% (PETG) | Too much cooling weakens layer adhesion; too little causes stringing |


## Post-Processing

1. **Remove brim** with a deburring tool or flush cutters.
2. **Light sanding** of the front face (the bed-contact surface) with 220-grit sandpaper to smooth any elephant's foot or brim remnants.
3. **Test-fit the Mac Studio** before mounting. It should slide in from the back with slight clearance on all sides. The rear bottom tips are softened on the outer baseplate profile for handling comfort, but the vent circle and rear channel opening are unchanged from the original fit geometry. The front and top openings now use smaller-radius corners with a light chamfer on the exterior edge; if your printer leaves any lip or elephant's foot there, lightly sand those beveled edges before judging cable clearance. If the fit is too tight overall, lightly sand the interior walls.
4. **Check screw slot alignment** by holding the enclosure against your mounting bracket and passing M5 bolts through the slots. The 10 mm slot length provides adjustment travel.


## Pre-Print Checklist

- [ ] Printer Z height ≥ 110 mm
- [ ] Bed size ≥ 210 × 210 mm
- [ ] PETG filament (or ASA if enclosed printer)
- [ ] Bed cleaned and leveled
- [ ] Brim enabled
- [ ] Supports off by default; enable only if your slicer preview shows a problem area
- [ ] Wall count set to fill 4 mm solid (8+ perimeters at 0.4 mm nozzle)
