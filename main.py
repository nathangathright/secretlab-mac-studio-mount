#!/usr/bin/env python3
"""Generate the enclosure CAD artifacts and generated reference docs."""

from __future__ import annotations

import argparse
import hashlib
import math
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from textwrap import dedent


ROOT = Path(__file__).resolve().parent
DEFAULT_SCAD_PATH = ROOT / "mac_studio_enclosure.scad"
DEFAULT_STL_PATH = ROOT / "mac_studio_enclosure.stl"
DEFAULT_ASSEMBLY_STL_PATH = ROOT / "mac_studio_enclosure_with_mac_studio.stl"
DEFAULT_ASSEMBLY_GLASS_USDZ_PATH = ROOT / "mac_studio_enclosure_with_mac_studio_glass.usdz"
DEFAULT_PRINTING_PATH = ROOT / "PRINTING.md"
DEFAULT_SPEC_PATH = ROOT / "mac_studio_enclosure_spec.txt"
DEFAULT_MAC_STUDIO_USDZ_PATH = ROOT / "mac-studio.usdz"
DEFAULT_BLENDER_BIN = "/Applications/Blender.app/Contents/MacOS/Blender"
DEFAULT_USDZIP_BIN = "/usr/bin/usdzip"
TOKEN_PATTERN = re.compile(r"__[A-Z0-9_]+__")


@dataclass(frozen=True)
class EnclosureInputs:
    """Authoritative measured dimensions and tunable geometry inputs."""

    body_w: float = 197
    body_h: float = 95
    corner_r: float = 30.4
    base_circle_d: float = 179.2
    base_protrusion: float = 8

    side_clearance: float = 7.0
    tb_clearance: float = 4.5
    wall: float = 6

    front_w_margin: float = 5
    front_h_margin: float = 15
    front_cutout_extra_w: float = 12
    front_cutout_cr: float = 3
    front_cutout_chamfer: float = 1.5

    rear_tip_outer_r: float = 4
    rear_tip_leg_angle: float = 126.56

    slot_w: float = 5
    slot_l: float = 10
    slot_rect_w: float = 50
    slot_rect_h: float = 30
    slot_top_offset: float = 14
    slot_head_max_d: float = 9.5
    slot_head_clearance: float = 0.5
    slot_counterbore_depth: float = 4.0

    fn: int = 80


@dataclass(frozen=True)
class PrintingGuide:
    """Authoritative print recommendations that feed the generated guide."""

    material: str = "PETG"
    alternate_material: str = "ASA"
    avoid_material: str = "PLA"
    layer_height: float = 0.20
    nozzle: float = 0.4
    alternate_nozzle: float = 0.6
    reference_line_width: float = 0.45
    brim_min: int = 5
    brim_max: int = 8
    top_bottom_layers: str = "10-12"
    print_speed: str = "40-60 mm/s (PETG)"
    outer_wall_speed: str = "30-40 mm/s"
    nozzle_temp: str = "230-245 °C (PETG)"
    bed_temp: str = "70-80 °C (PETG)"
    cooling_fan: str = "30-50% (PETG)"

    def perimeter_range(self, wall: float) -> tuple[int, int]:
        lower = max(1, math.floor(wall / self.reference_line_width))
        upper = max(lower, math.ceil(wall / self.reference_line_width))
        return lower, upper


@dataclass(frozen=True)
class VisualizationSettings:
    """Authoritative rendering settings for reference assembly previews."""

    glass_color_r: float = 0.82
    glass_color_g: float = 0.90
    glass_color_b: float = 0.96
    glass_opacity: float = 0.22
    glass_roughness: float = 0.08
    glass_ior: float = 1.45

    @property
    def glass_color(self) -> tuple[float, float, float]:
        return (self.glass_color_r, self.glass_color_g, self.glass_color_b)


REFERENCE_MAC_STUDIO_ASSET_PREFERRED_ROTATION_DEG = (270, 0, 180)
REFERENCE_MAC_STUDIO_ASSET_CANDIDATE_ROTATIONS_DEG = (
    REFERENCE_MAC_STUDIO_ASSET_PREFERRED_ROTATION_DEG,
    (0, 0, 0),
    (0, 0, 90),
    (0, 0, 180),
    (0, 0, 270),
    (90, 0, 0),
    (90, 0, 90),
    (90, 0, 180),
    (90, 0, 270),
    (180, 0, 0),
    (180, 0, 90),
    (180, 0, 180),
    (180, 0, 270),
    (270, 0, 0),
    (270, 0, 90),
    (270, 0, 270),
    (0, 90, 0),
    (0, 90, 90),
    (0, 90, 180),
    (0, 90, 270),
    (0, 270, 0),
    (0, 270, 90),
    (0, 270, 180),
    (0, 270, 270),
)


@dataclass(frozen=True)
class ReferenceAssemblyPlacement:
    """Shared placement settings for enclosure + Mac Studio reference assemblies."""

    target_dims_mm: tuple[float, float, float]
    body_center_vertical_offset_mm: float
    preferred_rotation_deg: tuple[int, int, int]
    candidate_rotations_deg: tuple[tuple[int, int, int], ...]


@dataclass(frozen=True)
class Geometry:
    """Derived enclosure geometry computed from the authoritative inputs."""

    inputs: EnclosureInputs

    @property
    def enc_w(self) -> float:
        return self.inputs.body_w + 2 * self.inputs.side_clearance

    @property
    def enc_d(self) -> float:
        return self.inputs.body_w + 2 * self.inputs.side_clearance

    @property
    def enc_h(self) -> float:
        return self.inputs.body_h + 2 * self.inputs.tb_clearance

    @property
    def enc_cr(self) -> float:
        return self.inputs.corner_r + self.inputs.side_clearance

    @property
    def inner_cr(self) -> float:
        return self.enc_cr - self.inputs.wall

    @property
    def front_cutout_w(self) -> float:
        return (
            self.enc_w
            - 2 * self.enc_cr
            - 2 * self.inputs.front_w_margin
            + self.inputs.front_cutout_extra_w
        )

    @property
    def front_cutout_h(self) -> float:
        return self.enc_h - 2 * self.inputs.front_h_margin

    @property
    def top_cutout_side(self) -> float:
        return self.front_cutout_w

    @property
    def slot_travel(self) -> float:
        return self.inputs.slot_l - self.inputs.slot_w

    @property
    def slot_counterbore_w(self) -> float:
        return self.inputs.slot_head_max_d + self.inputs.slot_head_clearance

    @property
    def slot_counterbore_l(self) -> float:
        return self.slot_counterbore_w + self.slot_travel

    @property
    def slot_depth_center(self) -> float:
        return self.enc_d / 2

    @property
    def slot_y_top(self) -> float:
        return self.enc_h / 2 - self.inputs.slot_top_offset

    @property
    def slot_y_bot(self) -> float:
        return self.slot_y_top - self.inputs.slot_rect_h

    @property
    def slot_z_front(self) -> float:
        return self.slot_depth_center - self.inputs.slot_rect_w / 2

    @property
    def slot_z_back(self) -> float:
        return self.slot_depth_center + self.inputs.slot_rect_w / 2

    @property
    def slot_angle(self) -> float:
        return math.degrees(
            math.atan2(self.inputs.slot_rect_w / 2, self.inputs.slot_rect_h / 2)
        )

    @property
    def rear_channel_half_w(self) -> float:
        return self.inputs.base_circle_d / 2

    @property
    def outer_rear_corner_x(self) -> float:
        return self.enc_w / 2 - self.enc_cr

    @property
    def outer_rear_corner_z(self) -> float:
        return self.enc_d - self.enc_cr

    @property
    def rear_tip_circle_center_x(self) -> float:
        return self.rear_channel_half_w + self.inputs.rear_tip_outer_r

    @property
    def rear_tip_circle_center_radicand(self) -> float:
        return (
            (self.enc_cr - self.inputs.rear_tip_outer_r) ** 2
            - (self.rear_tip_circle_center_x - self.outer_rear_corner_x) ** 2
        )

    @property
    def rear_tip_circle_center_z(self) -> float:
        return self.outer_rear_corner_z + math.sqrt(self.rear_tip_circle_center_radicand)

    @property
    def rear_tip_strip_h(self) -> float:
        return self.enc_d - self.rear_tip_circle_center_z

    @property
    def rear_tip_trapezoid_half_delta(self) -> float:
        return self.rear_tip_strip_h / math.tan(
            math.radians(180 - self.inputs.rear_tip_leg_angle)
        )

    @property
    def rear_tip_trapezoid_long_half_w(self) -> float:
        return self.rear_tip_circle_center_x + self.rear_tip_trapezoid_half_delta

    @property
    def nominal_side_gap(self) -> float:
        return self.inputs.side_clearance - self.inputs.wall

    @property
    def top_flat_margin(self) -> float:
        return (self.enc_w - self.top_cutout_side) / 2

    @property
    def top_contact_area_estimate(self) -> float:
        return self.enc_w * self.enc_d - self.top_cutout_side * self.top_cutout_side

    @property
    def recommended_bed_size(self) -> int:
        return int(math.ceil(max(self.enc_w, self.enc_d) / 10.0) * 10)

    @property
    def bottom_row_top_offset(self) -> float:
        return self.inputs.slot_top_offset + self.inputs.slot_rect_h

    def validate(self) -> None:
        if self.inputs.slot_counterbore_depth >= self.inputs.wall:
            raise ValueError("slot_counterbore_depth must stay shallower than the wall")
        if self.rear_tip_circle_center_radicand <= 0:
            raise ValueError("rear_tip_outer_r is too large for the current rear corner geometry")


@dataclass(frozen=True)
class ProjectContext:
    """Single source of truth for geometry, docs, and reference-render settings."""

    inputs: EnclosureInputs = field(default_factory=EnclosureInputs)
    printing: PrintingGuide = field(default_factory=PrintingGuide)
    visualization: VisualizationSettings = field(default_factory=VisualizationSettings)

    @property
    def geometry(self) -> Geometry:
        geometry = Geometry(self.inputs)
        geometry.validate()
        return geometry


def reference_assembly_placement(context: ProjectContext) -> ReferenceAssemblyPlacement:
    """Return the authoritative Mac Studio placement settings for Blender workflows."""
    geometry = context.geometry
    return ReferenceAssemblyPlacement(
        target_dims_mm=(
            geometry.inputs.body_w,
            geometry.inputs.body_w,
            geometry.inputs.body_h,
        ),
        body_center_vertical_offset_mm=geometry.inputs.base_protrusion / 2.0,
        preferred_rotation_deg=REFERENCE_MAC_STUDIO_ASSET_PREFERRED_ROTATION_DEG,
        candidate_rotations_deg=REFERENCE_MAC_STUDIO_ASSET_CANDIDATE_ROTATIONS_DEG,
    )


def format_number(value: float, digits: int = 3) -> str:
    """Emit compact numeric literals for docs and OpenSCAD."""
    if float(value).is_integer():
        return str(int(round(value)))
    return f"{value:.{digits}f}".rstrip("0").rstrip(".")


def display_path(path: Path) -> str:
    """Show repo-relative paths when possible, otherwise fall back to absolute."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stl_triangle_signature(path: Path) -> tuple[tuple[tuple[float, float, float], ...], ...]:
    """Return a normalized triangle signature for ASCII STL files."""
    triangles: list[tuple[tuple[float, float, float], ...]] = []
    current_vertices: list[tuple[float, float, float]] = []
    text = path.read_text(encoding="utf-8", errors="ignore")

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("vertex "):
            continue
        parts = stripped.split()
        vertex = tuple(round(float(value), 6) for value in parts[1:4])
        current_vertices.append(vertex)
        if len(current_vertices) == 3:
            triangles.append(tuple(sorted(current_vertices)))
            current_vertices = []

    if not triangles or current_vertices:
        raise ValueError(f"Could not parse a stable ASCII STL signature from {path}")

    return tuple(sorted(triangles))


def stl_files_match(path_a: Path, path_b: Path) -> bool:
    """Compare STL meshes while tolerating harmless facet-order differences."""
    try:
        return stl_triangle_signature(path_a) == stl_triangle_signature(path_b)
    except ValueError:
        return sha256_file(path_a) == sha256_file(path_b)


def reference_assembly_context_signature(context: ProjectContext) -> str:
    """Return a stable signature for assembly exports derived from main.py."""
    parts: list[str] = []
    for section_name, section in (
        ("inputs", context.inputs),
        ("visualization", context.visualization),
    ):
        for field_name in section.__dataclass_fields__:
            parts.append(f"{section_name}.{field_name}={getattr(section, field_name)!r}")
    payload = "|".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def read_usdz_root_text(usdz_path: Path) -> tuple[str, str]:
    """Return the root USDA filename and decoded text from a packaged USDZ."""
    with zipfile.ZipFile(usdz_path) as archive:
        root_candidates = [name for name in archive.namelist() if name.endswith(".usda")]
        if not root_candidates:
            raise ValueError(f"USDZ package {usdz_path} did not contain a USDA root layer")
        root_name = sorted(root_candidates)[0]
        return root_name, archive.read(root_name).decode("utf-8", errors="ignore")


def validate_reference_assembly_glass_usdz(
    assembly_usdz_path: Path,
    context: ProjectContext,
) -> list[str]:
    """Validate the semantic markers in the packaged glass USDZ assembly."""
    failures: list[str] = []

    try:
        _, root_text = read_usdz_root_text(assembly_usdz_path)
    except (ValueError, zipfile.BadZipFile) as exc:
        return [f"Unreadable USDZ package: {display_path(assembly_usdz_path)} ({exc})"]

    expected_signature = reference_assembly_context_signature(context)
    if expected_signature not in root_text:
        failures.append(
            f"Out of sync: {display_path(assembly_usdz_path)} (context signature mismatch)"
        )

    material_marker = 'def Material "EnclosureGlass"'
    material_start = root_text.find(material_marker)
    if material_start == -1:
        failures.append(
            f"Out of sync: {display_path(assembly_usdz_path)} (missing EnclosureGlass material)"
        )
        return failures

    next_material_match = re.search(
        r"\n\s*def Material \"", root_text[material_start + len(material_marker) :]
    )
    material_end = (
        material_start + len(material_marker) + next_material_match.start()
        if next_material_match
        else len(root_text)
    )
    material_block = root_text[material_start:material_end]
    expected_opacity = format_number(context.visualization.glass_opacity, 3)
    if f"float inputs:opacity = {expected_opacity}" not in material_block:
        failures.append(
            f"Out of sync: {display_path(assembly_usdz_path)} (glass opacity mismatch)"
        )

    return failures


def replace_tokens(template: str, replacements: dict[str, str]) -> str:
    rendered = template
    for token, replacement in replacements.items():
        rendered = rendered.replace(token, replacement)

    missing_tokens = sorted(set(TOKEN_PATTERN.findall(rendered)))
    if missing_tokens:
        raise ValueError(f"Failed to replace template tokens: {', '.join(missing_tokens)}")
    return rendered


def scad_replacements(context: ProjectContext) -> dict[str, str]:
    inputs = context.inputs
    geometry = context.geometry
    return {
        "__BODY_W__": format_number(inputs.body_w),
        "__BODY_H__": format_number(inputs.body_h),
        "__CORNER_R__": format_number(inputs.corner_r, 1),
        "__BASE_CIRCLE_D__": format_number(inputs.base_circle_d, 1),
        "__BASE_PROTRUSION__": format_number(inputs.base_protrusion),
        "__SIDE_CLEARANCE__": format_number(inputs.side_clearance, 1),
        "__TB_CLEARANCE__": format_number(inputs.tb_clearance, 1),
        "__WALL__": format_number(inputs.wall),
        "__ENC_W__": format_number(geometry.enc_w),
        "__ENC_D__": format_number(geometry.enc_d),
        "__ENC_H__": format_number(geometry.enc_h),
        "__ENC_CR__": format_number(geometry.enc_cr, 1),
        "__INNER_CR__": format_number(geometry.inner_cr, 1),
        "__FRONT_W_MARGIN__": format_number(inputs.front_w_margin),
        "__FRONT_H_MARGIN__": format_number(inputs.front_h_margin),
        "__FRONT_CUTOUT_EXTRA_W__": format_number(inputs.front_cutout_extra_w),
        "__FRONT_CUTOUT_W__": format_number(geometry.front_cutout_w, 1),
        "__FRONT_CUTOUT_H__": format_number(geometry.front_cutout_h),
        "__FRONT_CUTOUT_CR__": format_number(inputs.front_cutout_cr),
        "__FRONT_CUTOUT_CHAMFER__": format_number(inputs.front_cutout_chamfer, 1),
        "__TOP_CUTOUT_SIDE__": format_number(geometry.top_cutout_side, 1),
        "__REAR_TIP_OUTER_R__": format_number(inputs.rear_tip_outer_r),
        "__REAR_TIP_LEG_ANGLE__": format_number(inputs.rear_tip_leg_angle, 2),
        "__SLOT_W__": format_number(inputs.slot_w),
        "__SLOT_L__": format_number(inputs.slot_l),
        "__SLOT_RECT_W__": format_number(inputs.slot_rect_w),
        "__SLOT_RECT_H__": format_number(inputs.slot_rect_h),
        "__SLOT_TOP_OFFSET__": format_number(inputs.slot_top_offset),
        "__SLOT_HEAD_MAX_D__": format_number(inputs.slot_head_max_d, 1),
        "__SLOT_HEAD_CLEARANCE__": format_number(inputs.slot_head_clearance, 1),
        "__SLOT_COUNTERBORE_W__": format_number(geometry.slot_counterbore_w, 1),
        "__SLOT_COUNTERBORE_L__": format_number(geometry.slot_counterbore_l, 1),
        "__SLOT_COUNTERBORE_DEPTH__": format_number(inputs.slot_counterbore_depth, 1),
        "__SLOT_ANGLE__": format_number(geometry.slot_angle, 1),
        "__FN__": str(inputs.fn),
        "__PRINT_HEIGHT__": format_number(geometry.enc_h),
    }


def scad_header() -> str:
    lines = [
        "// Generated by main.py. Edit main.py to change geometry or generated docs.",
        "// Authoritative source of truth: main.py",
        "// Generated exports: mac_studio_enclosure.scad, mac_studio_enclosure.stl,",
        "// PRINTING.md, and mac_studio_enclosure_spec.txt",
        "",
    ]
    return "\n".join(lines)


def render_scad(context: ProjectContext) -> str:
    return f"{scad_header()}{replace_tokens(SCAD_TEMPLATE, scad_replacements(context))}"


def render_spec(context: ProjectContext) -> str:
    inputs = context.inputs
    geometry = context.geometry
    return dedent(
        f"""\
        Generated by main.py. Do not edit directly.
        This file is an export of the authoritative design context in main.py.

        MAC STUDIO UNDER-DESK ENCLOSURE — DESIGN SPECIFICATION
        ======================================================

        OVERVIEW
        --------
        A hollow, open-back enclosure sized to hold a Mac Studio on its side.
        The Mac Studio slides in from the back. The enclosure mounts under a
        desk via screw slots on two opposing faces.

        The authoritative measurements, formulas, and design rationale live in
        main.py. This text file is generated for convenient review and sharing.


        REFERENCE MEASUREMENTS TO TAKE FROM YOUR MAC STUDIO
        ---------------------------------------------------
        Measure the following from your Mac Studio with calipers:

          A.  Body width (square footprint, flat edge to flat edge)
          B.  Body height (top face to bottom face)
          C.  Body corner radius (the rounded vertical edges)
          D.  Front panel port area width
          E.  Front panel port area height
          F.  Front panel port area corner radius (if rounded)
          G.  Bottom base circle diameter (the raised or recessed ring
              on the underside — this is the ventilation intake zone)
          H.  Bottom base circle protrusion depth (how far the base
              extends below the main body, if at all)


        CURRENT BUILD VALUES FROM main.py
        ---------------------------------
          body_w (A)                  =  {format_number(inputs.body_w)} mm
          body_h (B)                  =  {format_number(inputs.body_h)} mm
          corner_r (C)                =  {format_number(inputs.corner_r, 1)} mm
          base_circle_d (G)           =  {format_number(inputs.base_circle_d, 1)} mm
          base_protrusion (H)         =  {format_number(inputs.base_protrusion)} mm
          side_clearance              =  {format_number(inputs.side_clearance, 1)} mm
          tb_clearance                =  {format_number(inputs.tb_clearance, 1)} mm
          wall                        =  {format_number(inputs.wall)} mm
          front_w_margin              =  {format_number(inputs.front_w_margin)} mm
          front_h_margin              =  {format_number(inputs.front_h_margin)} mm
          front_cutout_extra_w        =  {format_number(inputs.front_cutout_extra_w)} mm
          front_cutout_cr             =  {format_number(inputs.front_cutout_cr)} mm
          front_cutout_chamfer        =  {format_number(inputs.front_cutout_chamfer, 1)} mm
          rear_tip_outer_r            =  {format_number(inputs.rear_tip_outer_r)} mm
          rear_tip_leg_angle          =  {format_number(inputs.rear_tip_leg_angle, 2)} degrees
          slot_w                      =  {format_number(inputs.slot_w)} mm
          slot_l                      =  {format_number(inputs.slot_l)} mm
          slot_rect_w                 =  {format_number(inputs.slot_rect_w)} mm
          slot_rect_h                 =  {format_number(inputs.slot_rect_h)} mm
          slot_top_offset             =  {format_number(inputs.slot_top_offset)} mm
          slot_head_max_d             =  {format_number(inputs.slot_head_max_d, 1)} mm
          slot_head_clearance         =  {format_number(inputs.slot_head_clearance, 1)} mm
          slot_counterbore_depth      =  {format_number(inputs.slot_counterbore_depth, 1)} mm


        MAIN BODY
        ---------
        The enclosure is a cuboid shell that wraps the Mac Studio with a
        small but intentional air gap around the body.

        In the current design, the side walls grew thicker so the supplied M5
        mounting hardware can sit below the interior wall surface. The outer
        envelope therefore grows more than the actual body gap:

          Enclosure width  =  A + 14 mm
          Enclosure depth  =  A + 14 mm  (same, since the footprint is square)
          Enclosure height =  B + 9 mm

        With the current build values in main.py:

          Enclosure width  =  {format_number(geometry.enc_w)} mm
          Enclosure depth  =  {format_number(geometry.enc_d)} mm
          Enclosure height =  {format_number(geometry.enc_h)} mm

        The current side-wall gap resolves to about
        {format_number(geometry.nominal_side_gap, 1)} mm per side on the screw-wall axis.

        All four long edges of the cuboid are rounded. The enclosure corner
        radius should match the Mac Studio's own corner profile plus the
        same clearance:

          Enclosure corner radius  =  C + side_clearance
          Inner corner radius      =  enclosure corner radius - wall

        With the current build values:

          Enclosure corner radius  =  {format_number(geometry.enc_cr, 1)} mm
          Inner corner radius      =  {format_number(geometry.inner_cr, 1)} mm

        The enclosure is hollow with a uniform wall thickness of
        {format_number(inputs.wall)} mm. This is a structural choice rather than a
        measured Mac Studio dimension. The extra thickness leaves enough material
        behind the interior screw-head recesses while keeping the shell rigid
        without relying on infill.


        FACE DEFINITIONS
        ----------------
        Orient the model so the front face (where the Mac Studio's front
        ports are) faces you:

          Front:   Width x Height  (display/port cutout)
          Back:    Width x Height  (entirely open)
          Left:    Depth x Height  (screw slots)
          Right:   Depth x Height  (screw slots)
          Top:     Width x Depth   (square cutout)
          Bottom:  Width x Depth   (circular cutout and channel)


        BACK — OPEN
        -----------
        The entire back face is removed. The Mac Studio slides in from this
        side, and all rear ports and the power cable remain accessible.


        FRONT — PORT/DISPLAY CUTOUT
        ---------------------------
        A rectangular cutout on the front face, centered both horizontally
        and vertically, passing fully through the {format_number(inputs.wall)} mm wall.

        The implemented opening keeps the cutout centered, increases its width,
        reduces its corner radius, and adds a light chamfer on the exterior
        edge of the wall:

          Cutout width   =  enclosure width
                           - 2 x enclosure corner radius
                           - 2 x front-width margin
                           + {format_number(inputs.front_cutout_extra_w)} mm extra width

          Cutout height  =  enclosure height - 2 x front-height margin

        With the current build values:

          Cutout width   =  {format_number(geometry.front_cutout_w, 1)} mm
          Cutout height  =  {format_number(geometry.front_cutout_h)} mm

        All four corners of this cutout are rounded with a small radius:

          Cutout corner radius  =  {format_number(inputs.front_cutout_cr)} mm

        The outer edge of the front wall is chamfered around the opening:

          Front cutout chamfer  =  {format_number(inputs.front_cutout_chamfer, 1)} mm


        TOP — SQUARE CUTOUT
        -------------------
        A square cutout centered on the top face, passing fully through the
        {format_number(inputs.wall)} mm wall. This saves material and can aid ventilation.

        The current design ties the top opening directly to the front opening
        width for visual consistency:

          Top cutout side       =  front cutout width
          Top cutout corner r   =  front cutout corner r
          Top cutout chamfer    =  front cutout chamfer

        With the current build values:

          Top cutout side       =  {format_number(geometry.top_cutout_side, 1)} mm
          Top cutout corner r   =  {format_number(inputs.front_cutout_cr)} mm
          Top cutout chamfer    =  {format_number(inputs.front_cutout_chamfer, 1)} mm

        That still leaves roughly {format_number(geometry.top_flat_margin, 1)} mm of material
        between the opening and the outer edge on each flat side of the
        {format_number(geometry.enc_w)} mm top face.


        BOTTOM — CIRCULAR CUTOUT AND CHANNEL
        ------------------------------------
        A circular cutout centered on the bottom face, passing fully through
        the {format_number(inputs.wall)} mm wall. This aligns with and exposes the
        Mac Studio's bottom ventilation intake.

          Circle diameter  =  G  (the diameter of the base ring/vent circle
            on the Mac Studio's underside)

        With the current build values:

          Circle diameter  =  {format_number(inputs.base_circle_d, 1)} mm

        The current model also keeps a rear channel from the widest point of the
        circle to the back edge so the base can slide in from the rear:

          Channel width   =  G
          Channel length  =  half the enclosure depth

        With the current build values:

          Channel width   =  {format_number(inputs.base_circle_d, 1)} mm
          Channel length  =  {format_number(geometry.enc_d / 2, 1)} mm

        The rear tips of the outer baseplate profile are softened for handling
        comfort, but that relief does not change the actual circle-plus-channel
        bottom opening.


        LEFT AND RIGHT SIDES — SCREW SLOTS
        ----------------------------------
        Each side face has four slotted holes for mounting hardware. The
        pattern is identical on both sides.

        Slot dimensions:
          Each slot is a stadium (oblong) shape, {format_number(inputs.slot_l)} mm long and
          {format_number(inputs.slot_w)} mm wide. The {format_number(inputs.slot_w)} mm width provides
          clearance for M5 bolts. The {format_number(inputs.slot_l)} mm length provides
          adjustment travel for alignment during installation.

          On the interior face, each slot also gets a matching oblong
          counterbore pocket:

            Counterbore width   =  {format_number(geometry.slot_counterbore_w, 1)} mm
            Counterbore length  =  {format_number(geometry.slot_counterbore_l, 1)} mm
            Counterbore depth   =  {format_number(inputs.slot_counterbore_depth, 1)} mm

          This pocket is sized around a {format_number(inputs.slot_head_max_d, 1)} mm maximum
          screw-head diameter and keeps either of the supplied M5 x 10 mm
          Secretlab screw styles below flush with the interior wall surface.

        Slot arrangement:
          The four slots form a rectangle on each side face:

            Rectangle width   =  {format_number(inputs.slot_rect_w)} mm  (along the depth axis)
            Rectangle height  =  {format_number(inputs.slot_rect_h)} mm  (along the height axis)

          The rectangle is centered along the depth of the face. The top
          edge is {format_number(inputs.slot_top_offset)} mm from the top of the enclosure.

          Slot center positions (measured from the top-front corner of the
          side face):

            Top-front:      {format_number(geometry.slot_z_front, 1)} mm from front,  {format_number(inputs.slot_top_offset)} mm from top
            Top-back:       {format_number(geometry.slot_z_back, 1)} mm from front,  {format_number(inputs.slot_top_offset)} mm from top
            Bottom-front:   {format_number(geometry.slot_z_front, 1)} mm from front,  {format_number(geometry.bottom_row_top_offset)} mm from top
            Bottom-back:    {format_number(geometry.slot_z_back, 1)} mm from front,  {format_number(geometry.bottom_row_top_offset)} mm from top

        Slot orientation:
          Each slot's long axis is angled to point toward the center of the
          {format_number(inputs.slot_rect_w)} x {format_number(inputs.slot_rect_h)} mm rectangle. Tightening the bolts tends to pull the
          enclosure toward a centered position on the mounting bracket.

          Current slot angle from vertical  =  approximately {format_number(geometry.slot_angle, 1)} degrees


        MOUNTING ORIENTATION
        --------------------
        In use, the enclosure hangs under a desk. One screw-slot face is
        fastened against the underside of the desk (or a mounting bracket
        attached to the desk). The opposite screw-slot face faces the floor.

        The Mac Studio sits on its side inside the enclosure. The open back
        faces outward for cable access, and the front cutout keeps the front
        ports and power indicator accessible.
        """
    ) + "\n"


def render_printing(context: ProjectContext) -> str:
    inputs = context.inputs
    geometry = context.geometry
    printing = context.printing
    perimeter_low, perimeter_high = printing.perimeter_range(inputs.wall)
    return dedent(
        f"""\
        <!-- Generated by main.py. Do not edit directly. -->

        # 3D Printing Instructions - Mac Studio Under-Desk Enclosure

        ## Print Orientation

        Print upside-down with the top face (square cutout) on the build plate and the bottom face (circular vent cutout / vent-ring face) facing up.

        ```
                ┌── bottom face (circle+channel) ─┐
                │                                  │
                │         ▲ build direction        │
                │         │  ({format_number(geometry.enc_h)} mm)              │
                │   rounded corners run            │
                │   vertically along build axis    │
                │         │                        │
                ├─────────┴────────────────────────┤
                │   top face on bed (square cutout)│
                └──────────────────────────────────┘
                      {format_number(geometry.enc_w)} mm × {format_number(geometry.enc_d)} mm footprint
                      {format_number(geometry.enc_h)} mm tall print
        ```

        - **Best corner finish.** The four rounded edges run along the build axis. Each layer traces a smooth arc with no stairstepping on the main vertical corners.
        - **Strong bed adhesion.** The top face has a roughly {format_number(geometry.top_cutout_side, 1)} mm square cutout, leaving about a {format_number(geometry.top_flat_margin, 1)} mm-wide frame of contact area and roughly {format_number(geometry.top_contact_area_estimate, 0)} mm² of total bed contact.
        - **Smooth finish where it counts.** The top face, which is most visible when mounted, gets the smooth bed-contact surface.
        - **Still compact for the added hardware margin.** Only {format_number(geometry.enc_h)} mm tall.
        - **Usually no supports needed.** In the recommended orientation, the vent circle and rear channel open upward, so most slicers can print the shell cleanly without support material. If your slicer preview shows sagging bridges for your machine or material, add supports only where needed.
        - **Strong layer orientation.** Mounting screw loads go through the side walls in shear, not in layer-separating tension.
        - **Requires a {geometry.recommended_bed_size}+ mm bed** in both X and Y.

        ## Material

        **{printing.material} — recommended.** Best overall balance of strength, heat tolerance, and printability.

        | Material | Heat Deflection | Strength | Printability | Verdict |
        |----------|----------------|----------|-------------|---------|
        | **{printing.material}** | ~80 °C | Good | Easy | **Recommended** |
        | {printing.alternate_material} | ~100 °C | Very good | Moderate (needs enclosure, ventilation) | Best if you have an enclosed printer |
        | ABS | ~100 °C | Good | Difficult (warps badly at a {format_number(geometry.enc_w)} mm footprint) | Not recommended at this size |
        | {printing.avoid_material} | ~55 °C | Adequate | Easiest | **Do not use** — Mac Studio exhaust heat will soften it over time |
        | PA/Nylon | ~180 °C | Excellent | Difficult (moisture-sensitive) | Overkill, but works if you have the setup |

        **Why not {printing.avoid_material}?** The Mac Studio's exhaust can sustain 50-60 °C at the vent surface. {printing.avoid_material}'s heat deflection temperature is around 55 °C. Under sustained load, the enclosure will creep and deform. {printing.material}'s higher heat tolerance provides a much better margin.

        **Why not ABS?** ABS has excellent heat resistance but shrinks significantly as it cools. On a {format_number(geometry.enc_w)} mm footprint, warping is very likely unless you have an actively heated chamber. {printing.alternate_material} is a better alternative with similar thermal properties and less warping.

        ## Print Settings

        | Setting | Value | Rationale |
        |---------|-------|-----------|
        | Layer height | {format_number(printing.layer_height, 2)} mm | Good balance of speed and surface quality |
        | Nozzle | {format_number(printing.nozzle, 1)} mm | Standard; {format_number(printing.alternate_nozzle, 1)} mm also works and cuts print time significantly |
        | Wall count / perimeters | {perimeter_low}-{perimeter_high} | Fills the {format_number(inputs.wall)} mm wall almost entirely with perimeters. At {format_number(printing.reference_line_width, 2)} mm line width, {perimeter_low} perimeters ≈ {format_number(perimeter_low * printing.reference_line_width, 2)} mm and {perimeter_high} perimeters ≈ {format_number(perimeter_high * printing.reference_line_width, 2)} mm. |
        | Top / bottom solid layers | {printing.top_bottom_layers} | Keeps the smaller horizontal bridges and edge transitions well supported |
        | Infill | 0% | Not needed — the shell is driven by thick walls and perimeter structure |
        | Bed adhesion | Brim, {printing.brim_min}-{printing.brim_max} mm | Helps resist corner lift on a {format_number(geometry.enc_w)} mm footprint |
        | Supports | Off by default | Usually not needed in the recommended orientation; check your slicer preview before enabling them |
        | Print speed | {printing.print_speed} | Conservative speed for good layer adhesion. Outer walls at {printing.outer_wall_speed} for surface finish. |
        | Nozzle temp | {printing.nozzle_temp} | Check your filament's datasheet. Higher values usually improve layer bonding. |
        | Bed temp | {printing.bed_temp} | Standard for {printing.material} adhesion |
        | Cooling fan | {printing.cooling_fan} | Too much cooling weakens layer adhesion; too little causes stringing |

        ## Post-Processing

        1. **Remove the brim** with a deburring tool or flush cutters.
        2. **Lightly sand the front face** (the bed-contact surface) with 220-grit sandpaper to smooth any elephant's foot or brim remnants.
        3. **Test-fit the Mac Studio** before mounting. The current slot-wall gap is intentionally tight, so expect about {format_number(geometry.nominal_side_gap, 1)} mm of nominal clearance per side on that axis. The rear bottom tips are softened on the outer baseplate profile for handling comfort, but the vent circle and rear channel opening are unchanged from the original fit geometry.
        4. **Add felt pads if needed** to eliminate play. Thin adhesive felt, about 0.5-1.0 mm thick, works well. Use a few small pads instead of long strips. Keep pads clear of the bottom vent opening, the rear slide-in path, and the front opening edges.
        5. **Check screw slot alignment** by holding the enclosure against your mounting bracket and passing M5 bolts through the slots. The {format_number(inputs.slot_l)} mm slot length provides adjustment travel, and the interior counterbores should leave both the button-head and pan-head screw options below flush.

        ## Pre-Print Checklist

        - [ ] Printer Z height ≥ {format_number(geometry.enc_h + 6)} mm
        - [ ] Bed size ≥ {geometry.recommended_bed_size} × {geometry.recommended_bed_size} mm
        - [ ] {printing.material} filament (or {printing.alternate_material} if you have an enclosed printer)
        - [ ] Bed cleaned and leveled
        - [ ] Brim enabled
        - [ ] Supports off by default; enable only if your slicer preview shows a problem area
        - [ ] Wall count set to {perimeter_low}-{perimeter_high} perimeters to fill the {format_number(inputs.wall)} mm wall
        """
    ) + "\n"


def render_text_outputs(
    context: ProjectContext,
    scad_path: Path,
    printing_path: Path,
    spec_path: Path,
) -> dict[Path, str]:
    return {
        scad_path: render_scad(context),
        printing_path: render_printing(context),
        spec_path: render_spec(context),
    }


def write_text_outputs(text_outputs: dict[Path, str]) -> None:
    for path, text in text_outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def require_executable(executable: str, label: str) -> None:
    candidate = Path(executable)
    if shutil.which(executable) is None and not candidate.exists():
        raise FileNotFoundError(
            f"{label} binary '{executable}' was not found. Install {label} or pass the matching CLI flag."
        )


def validate_reference_assembly_inputs(
    enclosure_stl_path: Path,
    mac_studio_usdz_path: Path,
) -> None:
    if not enclosure_stl_path.exists():
        raise FileNotFoundError(
            f"Enclosure STL '{enclosure_stl_path}' does not exist. Generate it first or omit --skip-stl."
        )
    if not mac_studio_usdz_path.exists():
        raise FileNotFoundError(
            f"Mac Studio USDZ '{mac_studio_usdz_path}' does not exist."
        )


def build_blender_assembly_script(
    context: ProjectContext,
    enclosure_stl_path: Path,
    mac_studio_usdz_path: Path,
    export_block: str,
) -> str:
    placement = reference_assembly_placement(context)
    visualization = context.visualization

    script = BLENDER_ASSEMBLY_TEMPLATE.format(
        enclosure_stl_path=str(enclosure_stl_path),
        mac_studio_usdz_path=str(mac_studio_usdz_path),
        target_dims_mm=", ".join(f"{value:.6f}" for value in placement.target_dims_mm),
        body_center_vertical_offset_mm=f"{placement.body_center_vertical_offset_mm:.6f}",
        context_signature=reference_assembly_context_signature(context),
        glass_color=", ".join(f"{value:.6f}" for value in visualization.glass_color),
        glass_roughness=f"{visualization.glass_roughness:.6f}",
        glass_ior=f"{visualization.glass_ior:.6f}",
        preferred_rotation_deg=", ".join(str(value) for value in placement.preferred_rotation_deg),
        fallback_candidate_rotations_deg=",\n    ".join(
            f"({', '.join(str(value) for value in rotation_deg)})"
            for rotation_deg in placement.candidate_rotations_deg[1:]
        ),
    )
    return script.replace("__EXPORT_BLOCK__", export_block)


def run_blender_script(blender_bin: str, script: str, failure_message: str) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as handle:
        handle.write(script)
        script_path = Path(handle.name)

    try:
        result = subprocess.run(
            [blender_bin, "--background", "--python", str(script_path)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
    finally:
        script_path.unlink(missing_ok=True)

    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip() or failure_message
        raise RuntimeError(message)


def patch_usda_material_opacity(usda_path: Path, material_name: str, opacity: float) -> None:
    text = usda_path.read_text(encoding="utf-8")
    material_marker = f'def Material "{material_name}"'
    material_start = text.find(material_marker)
    if material_start == -1:
        raise ValueError(f"Could not find USD material '{material_name}' in {usda_path}")

    remaining = text[material_start + len(material_marker) :]
    next_material_match = re.search(r"\n\s*def Material \"", remaining)
    material_end = (
        material_start + len(material_marker) + next_material_match.start()
        if next_material_match
        else len(text)
    )
    material_block = text[material_start:material_end]
    opacity_text = format_number(opacity, 3)
    updated_block, replacements = re.subn(
        r"(float inputs:opacity = )([0-9.]+)",
        rf"\g<1>{opacity_text}",
        material_block,
        count=1,
    )
    if replacements != 1:
        raise ValueError(
            f"Could not find a preview-surface opacity input for USD material '{material_name}'"
        )

    usda_path.write_text(
        text[:material_start] + updated_block + text[material_end:],
        encoding="utf-8",
    )


def package_usdz(
    usdzip_bin: str,
    source_root: Path,
    root_layer_path: Path,
    output_usdz_path: Path,
) -> None:
    files = [root_layer_path.name]
    files.extend(
        str(path.relative_to(source_root))
        for path in sorted(source_root.rglob("*"))
        if path.is_file() and path != root_layer_path
    )

    output_usdz_path.parent.mkdir(parents=True, exist_ok=True)
    output_usdz_path.unlink(missing_ok=True)
    result = subprocess.run(
        [usdzip_bin, str(output_usdz_path), *files],
        cwd=source_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip() or "USDZ packaging failed."
        raise RuntimeError(message)


def export_stl(openscad_bin: str, scad_path: Path, stl_path: Path) -> None:
    require_executable(openscad_bin, "OpenSCAD")

    stl_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [openscad_bin, "-o", str(stl_path), str(scad_path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip() or "OpenSCAD export failed."
        raise RuntimeError(message)


def export_reference_assembly_stl(
    blender_bin: str,
    enclosure_stl_path: Path,
    assembly_stl_path: Path,
    mac_studio_usdz_path: Path,
    context: ProjectContext,
) -> None:
    require_executable(blender_bin, "Blender")
    validate_reference_assembly_inputs(enclosure_stl_path, mac_studio_usdz_path)

    export_block = BLENDER_STL_EXPORT_BLOCK.format(assembly_stl_path=str(assembly_stl_path))
    script = build_blender_assembly_script(
        context=context,
        enclosure_stl_path=enclosure_stl_path,
        mac_studio_usdz_path=mac_studio_usdz_path,
        export_block=export_block,
    )
    assembly_stl_path.parent.mkdir(parents=True, exist_ok=True)
    run_blender_script(blender_bin, script, "Blender assembly STL export failed.")


def export_reference_assembly_glass_usdz(
    blender_bin: str,
    usdzip_bin: str,
    enclosure_stl_path: Path,
    assembly_usdz_path: Path,
    mac_studio_usdz_path: Path,
    context: ProjectContext,
) -> None:
    require_executable(blender_bin, "Blender")
    require_executable(usdzip_bin, "usdzip")
    validate_reference_assembly_inputs(enclosure_stl_path, mac_studio_usdz_path)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        temp_usda_path = temp_root / "mac_studio_enclosure_with_mac_studio_glass.usda"
        export_block = BLENDER_GLASS_USDA_EXPORT_BLOCK.format(
            assembly_usda_path=str(temp_usda_path)
        )
        script = build_blender_assembly_script(
            context=context,
            enclosure_stl_path=enclosure_stl_path,
            mac_studio_usdz_path=mac_studio_usdz_path,
            export_block=export_block,
        )
        run_blender_script(blender_bin, script, "Blender assembly USD export failed.")
        patch_usda_material_opacity(
            temp_usda_path,
            material_name="EnclosureGlass",
            opacity=context.visualization.glass_opacity,
        )
        package_usdz(
            usdzip_bin=usdzip_bin,
            source_root=temp_root,
            root_layer_path=temp_usda_path,
            output_usdz_path=assembly_usdz_path,
        )


def check_generated_outputs(
    context: ProjectContext,
    text_outputs: dict[Path, str],
    stl_path: Path,
    openscad_bin: str,
    skip_stl: bool,
    with_mac_studio_assembly: bool,
    assembly_stl_path: Path,
    with_mac_studio_glass_usdz: bool,
    assembly_glass_usdz_path: Path,
    blender_bin: str,
    mac_studio_usdz_path: Path,
) -> list[str]:
    failures: list[str] = []

    for path, expected_text in text_outputs.items():
        if not path.exists():
            failures.append(f"Missing generated file: {display_path(path)}")
            continue
        actual_text = path.read_text(encoding="utf-8")
        if actual_text != expected_text:
            failures.append(f"Out of sync: {display_path(path)}")

    if skip_stl:
        return failures

    scad_path = next(path for path in text_outputs if path.suffix == ".scad")
    if not stl_path.exists():
        failures.append(f"Missing generated file: {display_path(stl_path)}")
        return failures

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        temp_scad_path = temp_root / scad_path.name
        temp_stl_path = temp_root / stl_path.name
        temp_scad_path.write_text(text_outputs[scad_path], encoding="utf-8")
        export_stl(openscad_bin, temp_scad_path, temp_stl_path)
        if not stl_files_match(temp_stl_path, stl_path):
            failures.append(f"Out of sync: {display_path(stl_path)}")

        if with_mac_studio_assembly:
            if not assembly_stl_path.exists():
                failures.append(f"Missing generated file: {display_path(assembly_stl_path)}")
            else:
                temp_assembly_path = temp_root / assembly_stl_path.name
                export_reference_assembly_stl(
                    blender_bin=blender_bin,
                    enclosure_stl_path=temp_stl_path,
                    assembly_stl_path=temp_assembly_path,
                    mac_studio_usdz_path=mac_studio_usdz_path,
                    context=context,
                )
                if not stl_files_match(temp_assembly_path, assembly_stl_path):
                    failures.append(f"Out of sync: {display_path(assembly_stl_path)}")

        if with_mac_studio_glass_usdz:
            if not assembly_glass_usdz_path.exists():
                failures.append(
                    f"Missing generated file: {display_path(assembly_glass_usdz_path)}"
                )
            else:
                failures.extend(
                    validate_reference_assembly_glass_usdz(
                        assembly_usdz_path=assembly_glass_usdz_path,
                        context=context,
                    )
                )

    return failures


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--scad-path",
        type=Path,
        default=DEFAULT_SCAD_PATH,
        help="Path for the generated OpenSCAD file.",
    )
    parser.add_argument(
        "--stl-path",
        type=Path,
        default=DEFAULT_STL_PATH,
        help="Path for the generated STL file.",
    )
    parser.add_argument(
        "--assembly-stl-path",
        type=Path,
        default=DEFAULT_ASSEMBLY_STL_PATH,
        help="Path for the generated reference STL containing the enclosure and Mac Studio asset.",
    )
    parser.add_argument(
        "--assembly-glass-usdz-path",
        type=Path,
        default=DEFAULT_ASSEMBLY_GLASS_USDZ_PATH,
        help="Path for the generated glass USDZ assembly containing the enclosure and Mac Studio asset.",
    )
    parser.add_argument(
        "--printing-path",
        type=Path,
        default=DEFAULT_PRINTING_PATH,
        help="Path for the generated printing guide.",
    )
    parser.add_argument(
        "--spec-path",
        type=Path,
        default=DEFAULT_SPEC_PATH,
        help="Path for the generated plain-text design specification.",
    )
    parser.add_argument(
        "--openscad-bin",
        default="openscad",
        help="OpenSCAD executable to use when exporting or checking the STL.",
    )
    parser.add_argument(
        "--blender-bin",
        default=DEFAULT_BLENDER_BIN,
        help="Blender executable to use when exporting the reference assembly STL.",
    )
    parser.add_argument(
        "--usdzip-bin",
        default=DEFAULT_USDZIP_BIN,
        help="usdzip executable to use when packaging the glass USDZ assembly.",
    )
    parser.add_argument(
        "--mac-studio-usdz-path",
        type=Path,
        default=DEFAULT_MAC_STUDIO_USDZ_PATH,
        help="Path to the Mac Studio USDZ reference model.",
    )
    parser.add_argument(
        "--skip-stl",
        action="store_true",
        help="Generate only the text-based outputs and skip STL export.",
    )
    parser.add_argument(
        "--with-mac-studio-assembly",
        action="store_true",
        help="Also generate a reference STL with the Mac Studio USDZ asset placed inside the enclosure.",
    )
    parser.add_argument(
        "--with-mac-studio-glass-usdz",
        action="store_true",
        help="Also generate a glass USDZ assembly with the Mac Studio asset placed inside the enclosure.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify that generated files on disk match the authoritative context in main.py.",
    )
    parser.add_argument(
        "--print-context",
        action="store_true",
        help="Print a summary of the authoritative geometry and print settings.",
    )
    return parser


def print_context(context: ProjectContext) -> None:
    geometry = context.geometry
    printing = context.printing
    print("Authoritative context from main.py:")
    print(
        f"- enclosure envelope: {format_number(geometry.enc_w)} x "
        f"{format_number(geometry.enc_d)} x {format_number(geometry.enc_h)} mm"
    )
    print(
        f"- front cutout: {format_number(geometry.front_cutout_w, 1)} x "
        f"{format_number(geometry.front_cutout_h)} mm"
    )
    print(f"- top cutout: {format_number(geometry.top_cutout_side, 1)} mm square")
    print(
        f"- slot counterbore: {format_number(geometry.slot_counterbore_l, 1)} x "
        f"{format_number(geometry.slot_counterbore_w, 1)} x "
        f"{format_number(context.inputs.slot_counterbore_depth, 1)} mm"
    )
    print(
        f"- recommended minimum bed: {geometry.recommended_bed_size} x "
        f"{geometry.recommended_bed_size} mm"
    )
    print(f"- recommended material: {printing.material}")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.skip_stl and (args.with_mac_studio_assembly or args.with_mac_studio_glass_usdz):
        parser.error(
            "--with-mac-studio-assembly and --with-mac-studio-glass-usdz require STL generation; omit --skip-stl."
        )

    context = ProjectContext()
    if args.print_context:
        print_context(context)

    text_outputs = render_text_outputs(
        context=context,
        scad_path=args.scad_path,
        printing_path=args.printing_path,
        spec_path=args.spec_path,
    )

    if args.check:
        failures = check_generated_outputs(
            context=context,
            text_outputs=text_outputs,
            stl_path=args.stl_path,
            openscad_bin=args.openscad_bin,
            skip_stl=args.skip_stl,
            with_mac_studio_assembly=args.with_mac_studio_assembly,
            assembly_stl_path=args.assembly_stl_path,
            with_mac_studio_glass_usdz=args.with_mac_studio_glass_usdz,
            assembly_glass_usdz_path=args.assembly_glass_usdz_path,
            blender_bin=args.blender_bin,
            mac_studio_usdz_path=args.mac_studio_usdz_path,
        )
        if failures:
            for failure in failures:
                print(failure)
            return 1
        print("Generated outputs are in sync with main.py.")
        return 0

    write_text_outputs(text_outputs)
    for path in text_outputs:
        print(f"Wrote {display_path(path)}")

    if not args.skip_stl:
        export_stl(args.openscad_bin, args.scad_path, args.stl_path)
        print(f"Wrote {display_path(args.stl_path)}")

        if args.with_mac_studio_assembly:
            export_reference_assembly_stl(
                blender_bin=args.blender_bin,
                enclosure_stl_path=args.stl_path,
                assembly_stl_path=args.assembly_stl_path,
                mac_studio_usdz_path=args.mac_studio_usdz_path,
                context=context,
            )
            print(f"Wrote {display_path(args.assembly_stl_path)}")

        if args.with_mac_studio_glass_usdz:
            export_reference_assembly_glass_usdz(
                blender_bin=args.blender_bin,
                usdzip_bin=args.usdzip_bin,
                enclosure_stl_path=args.stl_path,
                assembly_usdz_path=args.assembly_glass_usdz_path,
                mac_studio_usdz_path=args.mac_studio_usdz_path,
                context=context,
            )
            print(f"Wrote {display_path(args.assembly_glass_usdz_path)}")

    return 0


BLENDER_ASSEMBLY_TEMPLATE = r"""
import bpy
import math
from pathlib import Path
from mathutils import Vector

ENCLOSURE_STL_PATH = r"{enclosure_stl_path}"
MAC_STUDIO_USDZ_PATH = r"{mac_studio_usdz_path}"
TARGET_DIMS_MM = Vector(({target_dims_mm}))
BODY_CENTER_VERTICAL_OFFSET_MM = {body_center_vertical_offset_mm}
CONTEXT_SIGNATURE = "{context_signature}"
GLASS_COLOR = ({glass_color})
GLASS_ROUGHNESS = {glass_roughness}
GLASS_IOR = {glass_ior}
PREFERRED_ROTATION_DEG = ({preferred_rotation_deg})
CANDIDATE_ROTATIONS_DEG = [
    PREFERRED_ROTATION_DEG,
    {fallback_candidate_rotations_deg},
]


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()

    for collection in (bpy.data.meshes, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
        for block in list(collection):
            if block.users == 0:
                collection.remove(block)


def mesh_objects(objects):
    return [obj for obj in objects if obj.type == "MESH"]


def world_bbox(objects):
    vertices = []
    for obj in mesh_objects(objects):
        vertices.extend(obj.matrix_world @ vertex.co for vertex in obj.data.vertices)

    mins = Vector((min(v.x for v in vertices), min(v.y for v in vertices), min(v.z for v in vertices)))
    maxs = Vector((max(v.x for v in vertices), max(v.y for v in vertices), max(v.z for v in vertices)))
    return mins, maxs


def bbox_center(objects):
    mins, maxs = world_bbox(objects)
    return (mins + maxs) / 2.0


def select_meshes(objects):
    bpy.ops.object.select_all(action="DESELECT")
    meshes = mesh_objects(objects)
    if not meshes:
        raise RuntimeError("Assembly export did not have any mesh objects to select.")
    for obj in meshes:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]


def apply_enclosure_glass_material(objects):
    material = bpy.data.materials.new(name="EnclosureGlass")
    material.use_nodes = True
    material.blend_method = "BLEND"
    if hasattr(material, "shadow_method"):
        material.shadow_method = "NONE"

    principled = material.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = (*GLASS_COLOR, 1.0)
    if "Transmission Weight" in principled.inputs:
        principled.inputs["Transmission Weight"].default_value = 1.0
    elif "Transmission" in principled.inputs:
        principled.inputs["Transmission"].default_value = 1.0
    if "IOR" in principled.inputs:
        principled.inputs["IOR"].default_value = GLASS_IOR
    principled.inputs["Roughness"].default_value = GLASS_ROUGHNESS

    for obj in mesh_objects(objects):
        obj.data.materials.clear()
        obj.data.materials.append(material)


def tag_reference_assembly(objects):
    for obj in objects:
        obj["codex_context_signature"] = CONTEXT_SIGNATURE


def import_enclosure():
    existing = set(bpy.data.objects)
    bpy.ops.wm.stl_import(filepath=ENCLOSURE_STL_PATH)
    imported = [obj for obj in bpy.data.objects if obj not in existing]
    meshes = mesh_objects(imported)
    if not meshes:
        raise RuntimeError("STL import did not create any mesh objects.")
    return meshes


def import_mac_studio():
    existing = set(bpy.data.objects)
    bpy.ops.wm.usd_import(filepath=MAC_STUDIO_USDZ_PATH)
    imported = [obj for obj in bpy.data.objects if obj not in existing]
    meshes = mesh_objects(imported)
    if not meshes:
        raise RuntimeError("USD import did not create any mesh objects.")
    return meshes


def parent_to_empty(objects, name):
    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    for obj in objects:
        obj.parent = root
        obj.matrix_parent_inverse = root.matrix_world.inverted()
    return root


def place_mac_studio(mac_meshes, enclosure_meshes):
    root = parent_to_empty(mac_meshes, "MacStudioAssemblyRoot")
    bpy.context.view_layer.update()

    # Preserve the previously validated front-port orientation while flipping the
    # vent toward the enclosure's vent face in print orientation.
    best_rotation = None
    best_fit_scale = None
    best_error = None

    for rotation_deg in CANDIDATE_ROTATIONS_DEG:
        root.rotation_euler = tuple(math.radians(value) for value in rotation_deg)
        root.scale = (1.0, 1.0, 1.0)
        bpy.context.view_layer.update()

        mac_mins, mac_maxs = world_bbox(mac_meshes)
        actual_dims = mac_maxs - mac_mins
        fit_scale = TARGET_DIMS_MM.dot(actual_dims) / max(actual_dims.dot(actual_dims), 1e-12)
        residual = TARGET_DIMS_MM - (actual_dims * fit_scale)
        error = residual.length

        if best_error is None or error < best_error:
            best_rotation = rotation_deg
            best_fit_scale = fit_scale
            best_error = error

    root.rotation_euler = tuple(math.radians(value) for value in best_rotation)
    root.scale = (best_fit_scale, best_fit_scale, best_fit_scale)
    bpy.context.view_layer.update()

    enclosure_center = bbox_center(enclosure_meshes)
    mac_center = bbox_center(mac_meshes)
    root.location += enclosure_center - mac_center
    # In print orientation, +Z is the enclosure's vent/foot side. Shift the
    # model so the main body (overall height minus vent/foot protrusion) is
    # centered in the cavity instead of centering the full external height.
    root.location.z += BODY_CENTER_VERTICAL_OFFSET_MM
    bpy.context.view_layer.update()


clear_scene()
enclosure_meshes = import_enclosure()
mac_meshes = import_mac_studio()
place_mac_studio(mac_meshes, enclosure_meshes)
__EXPORT_BLOCK__
"""


BLENDER_STL_EXPORT_BLOCK = r"""
tag_reference_assembly(enclosure_meshes + mac_meshes)
select_meshes(enclosure_meshes + mac_meshes)
bpy.ops.wm.stl_export(
    filepath=r"{assembly_stl_path}",
    ascii_format=True,
    export_selected_objects=True,
    global_scale=1.0,
    use_scene_unit=False,
)
"""


BLENDER_GLASS_USDA_EXPORT_BLOCK = r"""
ASSEMBLY_USDA_PATH = Path(r"{assembly_usda_path}")
apply_enclosure_glass_material(enclosure_meshes)
tag_reference_assembly(enclosure_meshes + mac_meshes)
select_meshes(enclosure_meshes + mac_meshes)
bpy.ops.wm.usd_export(
    filepath=str(ASSEMBLY_USDA_PATH),
    selected_objects_only=True,
    export_materials=True,
    export_custom_properties=True,
    generate_preview_surface=True,
    export_textures_mode="NEW",
    convert_scene_units="MILLIMETERS",
)
"""


SCAD_TEMPLATE = """// Mac Studio Under-Desk Enclosure
// Parametric design — all dimensions derived from Mac Studio measurements

// ── Mac Studio Measurements ──────────────────────────────────────────
body_w         = __BODY_W__;    // A: body width (square footprint, mm)
body_h         = __BODY_H__;    // B: body height (mm)
corner_r       = __CORNER_R__;  // C: body corner radius (mm)
base_circle_d  = __BASE_CIRCLE_D__;  // G: bottom vent ring diameter (mm)
base_protrusion = __BASE_PROTRUSION__;  // H: base ring depth below body (mm)

// ── Clearances ───────────────────────────────────────────────────────
// These values set the outer envelope. With a 6 mm wall, the current
// side-wall gap resolves to about 1.0 mm per side while the top/bottom
// envelope stays slightly more generous.
side_clearance = __SIDE_CLEARANCE__;  // enclosure growth per side on width/depth (mm)
tb_clearance   = __TB_CLEARANCE__;    // enclosure growth per side on height (mm)

// ── Wall ─────────────────────────────────────────────────────────────
wall = __WALL__;  // wall thickness (mm)

// ── Computed Enclosure Dimensions ────────────────────────────────────
enc_w  = body_w + 2 * side_clearance;   // __ENC_W__ mm
enc_d  = body_w + 2 * side_clearance;   // __ENC_D__ mm (square footprint)
enc_h  = body_h + 2 * tb_clearance;     // __ENC_H__ mm
enc_cr = corner_r + side_clearance;     // __ENC_CR__ mm outer corner radius
inner_cr = enc_cr - wall;               // __INNER_CR__ mm inner corner radius

// ── Front Cutout ─────────────────────────────────────────────────────
front_w_margin  = __FRONT_W_MARGIN__;   // margin inward from start of flat face (mm)
front_h_margin  = __FRONT_H_MARGIN__;   // margin from top/bottom enclosure edge (mm)
front_cutout_extra_w = __FRONT_CUTOUT_EXTRA_W__;  // centered width increase over the baseline formula
front_cutout_w  = enc_w - 2 * enc_cr - 2 * front_w_margin + front_cutout_extra_w;  // __FRONT_CUTOUT_W__ mm
front_cutout_h  = enc_h - 2 * front_h_margin;   // __FRONT_CUTOUT_H__ mm
front_cutout_cr = __FRONT_CUTOUT_CR__;  // tighter radius preserves width lower in the port band
front_cutout_chamfer = __FRONT_CUTOUT_CHAMFER__;  // front-face chamfer depth/width (mm)

// ── Top Cutout ───────────────────────────────────────────────────────
top_cutout_side = front_cutout_w;        // __TOP_CUTOUT_SIDE__ mm
top_cutout_cr   = front_cutout_cr;
top_cutout_chamfer = front_cutout_chamfer;

// ── Rear Tip Outer Profile ───────────────────────────────────────────
rear_tip_outer_r = __REAR_TIP_OUTER_R__;      // target rear tip round-over radius (mm)
rear_tip_leg_angle = __REAR_TIP_LEG_ANGLE__;  // interior angle of each trapezoid leg (deg)

// ── Screw Slot Parameters ────────────────────────────────────────────
slot_w = __SLOT_W__;      // slot width — M5 bolt clearance (mm)
slot_l = __SLOT_L__;      // slot length — adjustment travel (mm)
slot_travel = slot_l - slot_w;
slot_rect_w = __SLOT_RECT_W__;     // slot rectangle width along depth (mm)
slot_rect_h = __SLOT_RECT_H__;     // slot rectangle height (mm)
slot_top_offset = __SLOT_TOP_OFFSET__;  // top edge of rectangle from enclosure top (mm)

// Flush interior pockets sized for the largest supplied M5 head style.
slot_head_max_d = __SLOT_HEAD_MAX_D__;         // largest supported screw-head diameter (mm)
slot_head_clearance = __SLOT_HEAD_CLEARANCE__; // radial/print tolerance around the screw head (mm)
slot_counterbore_w = slot_head_max_d + slot_head_clearance;  // __SLOT_COUNTERBORE_W__ mm
slot_counterbore_l = slot_counterbore_w + slot_travel;       // __SLOT_COUNTERBORE_L__ mm
slot_counterbore_depth = __SLOT_COUNTERBORE_DEPTH__;         // mm

assert(
    slot_counterbore_depth < wall,
    "slot_counterbore_depth must stay shallower than the wall thickness"
);

// Slot center positions (from top-front corner of side face)
slot_depth_center = enc_d / 2;
slot_y_top  = enc_h / 2 - slot_top_offset;
slot_y_bot  = slot_y_top - slot_rect_h;
slot_z_front = slot_depth_center - slot_rect_w / 2;
slot_z_back  = slot_depth_center + slot_rect_w / 2;

// Slot convergence angle: atan2(half_rect_w, half_rect_h)
slot_angle = atan2(slot_rect_w / 2, slot_rect_h / 2);  // approximately __SLOT_ANGLE__ degrees

// ── Resolution ───────────────────────────────────────────────────────
$fn = __FN__;

// Rear tip outer profile geometry:
// 1. Start from the original outer baseplate footprint.
// 2. Remove a full-width rear strip down to the centers of the add-back circles.
// 3. Add two r=4 circles back at those centers.
// 4. Subtract the exact original vent circle + channel afterward.
//
// This keeps the final bottom cutout identical to the original model while
// changing only the outer silhouette of the rear baseplate tips.
rear_channel_half_w = base_circle_d / 2;
outer_rear_corner_x = enc_w / 2 - enc_cr;
outer_rear_corner_z = enc_d - enc_cr;
rear_tip_circle_center_x = rear_channel_half_w + rear_tip_outer_r;
rear_tip_circle_center_radicand =
    pow(enc_cr - rear_tip_outer_r, 2) -
    pow(rear_tip_circle_center_x - outer_rear_corner_x, 2);
assert(
    rear_tip_circle_center_radicand > 0,
    "rear_tip_outer_r is too large for the current rear corner geometry"
);
rear_tip_circle_center_z =
    outer_rear_corner_z + sqrt(rear_tip_circle_center_radicand);
rear_tip_strip_h = enc_d - rear_tip_circle_center_z;
rear_tip_trapezoid_half_delta =
    rear_tip_strip_h / tan(180 - rear_tip_leg_angle);
rear_tip_trapezoid_long_half_w =
    rear_tip_circle_center_x + rear_tip_trapezoid_half_delta;

// ═══════════════════════════════════════════════════════════════════════
// Helper Modules
// ═══════════════════════════════════════════════════════════════════════

// 2D rounded rectangle, centered at origin
module rounded_rect(w, h, r) {
    offset(r = r)
        square([w - 2 * r, h - 2 * r], center = true);
}

// 2D stadium (oblong): two semicircles joined by a rectangle
// length along X, width along Y
module stadium(length, width) {
    hull() {
        translate([-(length - width) / 2, 0])
            circle(d = width);
        translate([ (length - width) / 2, 0])
            circle(d = width);
    }
}

module slot_profile(length, width, angle) {
    rotate([0, 0, angle])
        stadium(length, width);
}

// ═══════════════════════════════════════════════════════════════════════
// Enclosure Components
// ═══════════════════════════════════════════════════════════════════════

// Rounded box: 4 rounded edges run along Y (height axis), at corners
// of the XZ (width x depth) footprint. Top/bottom faces are flat.
module rounded_box(w, d, h, cr) {
    hull() {
        for (x = [-(w/2 - cr), w/2 - cr])
        for (z = [cr, d - cr])
            translate([x, 0, z])
                rotate([-90, 0, 0])
                    cylinder(h = h, r = cr, center = true);
    }
}

// Main hollow shell: closed front/top/bottom/sides, open back
module shell() {
    difference() {
        rounded_box(enc_w, enc_d, enc_h, enc_cr);

        hull() {
            for (x = [-(enc_w/2 - wall - inner_cr), enc_w/2 - wall - inner_cr])
            for (z = [wall + inner_cr, enc_d + 1])
                translate([x, 0, z])
                    rotate([-90, 0, 0])
                        cylinder(h = enc_h - 2 * wall, r = inner_cr, center = true);
        }
    }
}

module front_cutout_profile() {
    rounded_rect(front_cutout_w, front_cutout_h, front_cutout_cr);
}

module front_cutout_chamfer() {
    eps = 0.01;

    hull() {
        translate([0, 0, -eps])
            linear_extrude(eps)
                offset(delta = front_cutout_chamfer)
                    front_cutout_profile();

        translate([0, 0, front_cutout_chamfer])
            linear_extrude(eps)
                front_cutout_profile();
    }
}

module front_cutout() {
    union() {
        translate([0, 0, -1])
            linear_extrude(wall + 2)
                front_cutout_profile();

        front_cutout_chamfer();
    }
}

module top_cutout_profile() {
    rounded_rect(top_cutout_side, top_cutout_side, top_cutout_cr);
}

module top_cutout_chamfer_profile() {
    eps = 0.01;
    top_outer_face_z = wall + 1;

    hull() {
        translate([0, 0, top_outer_face_z - top_cutout_chamfer])
            linear_extrude(eps)
                top_cutout_profile();

        translate([0, 0, top_outer_face_z - eps])
            linear_extrude(eps)
                offset(delta = top_cutout_chamfer)
                    top_cutout_profile();
    }
}

module top_cutout() {
    translate([0, enc_h / 2 - wall - 1, enc_d / 2])
        rotate([-90, 0, 0])
            union() {
                linear_extrude(wall + 2)
                    top_cutout_profile();

                top_cutout_chamfer_profile();
            }
}

module bottom_cutout_profile() {
    union() {
        circle(d = base_circle_d);
        translate([0, enc_d / 4])
            square([base_circle_d, enc_d / 2], center = true);
    }
}

module bottom_cutout() {
    translate([0, -(enc_h / 2 - wall - 1), enc_d / 2])
        rotate([90, 0, 0])
            linear_extrude(wall + 2)
                bottom_cutout_profile();
}

module rear_tip_relief_profile() {
    difference() {
        polygon(points = [
            [-rear_tip_circle_center_x, rear_tip_circle_center_z - enc_d / 2],
            [ rear_tip_circle_center_x, rear_tip_circle_center_z - enc_d / 2],
            [ rear_tip_trapezoid_long_half_w,  enc_d / 2 + 0.01],
            [-rear_tip_trapezoid_long_half_w,  enc_d / 2 + 0.01]
        ]);

        for (side_sign = [-1, 1])
            translate([
                side_sign * rear_tip_circle_center_x,
                rear_tip_circle_center_z - enc_d / 2
            ])
                circle(r = rear_tip_outer_r);
    }
}

module rear_tip_outer_relief_remove() {
    translate([0, -(enc_h / 2 - wall), enc_d / 2])
        rotate([90, 0, 0])
            linear_extrude(wall + 0.01)
                rear_tip_relief_profile();
}

module screw_slot(angle) {
    linear_extrude(wall + 2, center = true)
        slot_profile(slot_l, slot_w, angle);
}

// When `reverse_extrude` is true, the pocket is pushed into negative local Z so
// the left side can cut inward without mirroring the obround profile.
module screw_counterbore(angle, reverse_extrude = false) {
    counterbore_h = slot_counterbore_depth + 0.01;

    translate([0, 0, reverse_extrude ? -counterbore_h : 0])
        linear_extrude(counterbore_h, center = false)
            slot_profile(slot_counterbore_l, slot_counterbore_w, angle);
}

module side_slots(side_sign) {
    x_pos = side_sign * (enc_w / 2 - wall / 2);
    x_inner = side_sign * (enc_w / 2 - wall);
    counterbore_reverse_extrude = side_sign < 0;

    slot_positions = [
        [slot_z_front, slot_y_top,   slot_angle],
        [slot_z_back,  slot_y_top,  -slot_angle],
        [slot_z_front, slot_y_bot,  -slot_angle],
        [slot_z_back,  slot_y_bot,   slot_angle],
    ];

    for (s = slot_positions) {
        translate([x_pos, s[1], s[0]])
            rotate([0, 90, 0])
                screw_slot(s[2]);

        translate([x_inner, s[1], s[0]])
            rotate([0, 90, 0])
                screw_counterbore(s[2], counterbore_reverse_extrude);
    }
}

// ═══════════════════════════════════════════════════════════════════════
// Final Assembly
// ═══════════════════════════════════════════════════════════════════════

module enclosure_model() {
    difference() {
        shell();
        rear_tip_outer_relief_remove();
        front_cutout();
        top_cutout();
        bottom_cutout();
        side_slots(-1);
        side_slots(+1);
    }
}

// Export in the recommended print orientation:
// top face on the bed, vent-ring face up, __PRINT_HEIGHT__ mm tall in Z.
rotate([-90, 0, 0])
    enclosure_model();
"""


if __name__ == "__main__":
    raise SystemExit(main())
