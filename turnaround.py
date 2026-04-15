"""
Generate a 360-degree turnaround video of the Mac Studio enclosure.

The enclosure geometry and Mac Studio placement settings come from main.py.

Usage:
  /Applications/Blender.app/Contents/MacOS/Blender --background --python turnaround.py
  /Applications/Blender.app/Contents/MacOS/Blender --background --python turnaround.py -- --final
  /Applications/Blender.app/Contents/MacOS/Blender --background --python turnaround.py -- --frame
  /Applications/Blender.app/Contents/MacOS/Blender --background --python turnaround.py -- --include-mac-studio
"""

from __future__ import annotations

import argparse
import math
import subprocess
import sys
from pathlib import Path

import bpy
from mathutils import Vector


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import main as build_main


PROJECT_CONTEXT = build_main.ProjectContext()
ASSEMBLY_PLACEMENT = build_main.reference_assembly_placement(PROJECT_CONTEXT)

MODEL_PATH = build_main.DEFAULT_STL_PATH
MAC_STUDIO_PATH = build_main.DEFAULT_MAC_STUDIO_USDZ_PATH
OUTPUT_DIR = SCRIPT_DIR / "turnaround_output"

MODEL_SCALE_METERS = 0.001
TURNAROUND_DISPLAY_ROTATION_DEG = (180, 0, 0)
MAC_STUDIO_TARGET_DIMS_M = Vector(
    tuple(value * MODEL_SCALE_METERS for value in ASSEMBLY_PLACEMENT.target_dims_mm)
)
BODY_CENTER_VERTICAL_OFFSET_M = (
    ASSEMBLY_PLACEMENT.body_center_vertical_offset_mm * MODEL_SCALE_METERS
)
MAC_STUDIO_CANDIDATE_ROTATIONS_DEG = ASSEMBLY_PLACEMENT.candidate_rotations_deg

RENDER_PRESETS = {
    "final": {
        "resolution_x": 1920,
        "resolution_y": 1080,
        "fps": 30,
        "duration_seconds": 6,
        "samples": 128,
        "output_name": "turnaround.mp4",
    },
    "preview": {
        "resolution_x": 1280,
        "resolution_y": 720,
        "fps": 24,
        "duration_seconds": 4,
        "samples": 32,
        "output_name": "turnaround_preview.mp4",
    },
}

CAMERA_ELEVATION_DEG = 25
CAMERA_DISTANCE_FACTOR = 6.0
DEFAULT_STILL_FRAME = 25
ORTHO_FRONT_MARGIN = 1.15


def clear_scene():
    """Remove all objects and orphaned scene data."""
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()

    for collection in (bpy.data.meshes, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
        for block in list(collection):
            if block.users == 0:
                collection.remove(block)


def parse_args():
    """Parse script arguments passed after Blender's `--` separator."""
    script_argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--final",
        action="store_true",
        help="Render the full-quality mp4 instead of the default preview render.",
    )
    parser.add_argument(
        "--frame",
        nargs="?",
        const=DEFAULT_STILL_FRAME,
        type=int,
        help=(
            "Render a single still frame from the turnaround orbit. "
            f"If no frame is supplied, defaults to {DEFAULT_STILL_FRAME}."
        ),
    )
    parser.add_argument(
        "--include-mac-studio",
        action="store_true",
        help="Include the Mac Studio USDZ model inside the enclosure.",
    )
    parser.add_argument(
        "--orthographic-front",
        action="store_true",
        help="Use a static orthographic front camera instead of the turnaround orbit.",
    )

    args = parser.parse_args(script_argv)
    args.render_mode = "final" if args.final else "preview"
    return args


def get_mesh_objects(objects):
    """Return only mesh objects from an iterable."""
    return [obj for obj in objects if obj.type == "MESH"]


def get_world_vertices(objects):
    """Return all world-space vertices for the given mesh objects."""
    verts = []
    for obj in get_mesh_objects(objects):
        verts.extend(obj.matrix_world @ vertex.co for vertex in obj.data.vertices)
    return verts


def get_world_bbox(objects):
    """Return the world-space bounding box for the given mesh objects."""
    verts = get_world_vertices(objects)
    mins = Vector((min(v.x for v in verts), min(v.y for v in verts), min(v.z for v in verts)))
    maxs = Vector((max(v.x for v in verts), max(v.y for v in verts), max(v.z for v in verts)))
    return mins, maxs


def get_bbox_center(objects):
    """Return the center of the world-space bounding box."""
    mins, maxs = get_world_bbox(objects)
    return (mins + maxs) / 2.0


def get_bounding_radius(objects):
    """Return the radius of the bounding sphere of the mesh objects."""
    verts = get_world_vertices(objects)
    center = sum(verts, Vector()) / len(verts)
    return max((vertex - center).length for vertex in verts)


def select_mesh_objects(objects):
    """Select the mesh objects and make the first one active."""
    bpy.ops.object.select_all(action="DESELECT")
    meshes = get_mesh_objects(objects)
    if not meshes:
        raise RuntimeError("Expected at least one mesh object to select.")
    for obj in meshes:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]


def parent_objects_to_empty(objects, name, recenter=False):
    """Parent objects to a single empty, optionally recentering them around origin."""
    root = bpy.data.objects.new(name, None)
    if recenter:
        root.location = get_bbox_center(objects)
    bpy.context.collection.objects.link(root)
    for obj in objects:
        obj.parent = root
        obj.matrix_parent_inverse = root.matrix_world.inverted()
    if recenter:
        root.location = (0, 0, 0)
    bpy.context.view_layer.update()
    return root


def shade_auto_smooth(objects):
    """Enable Blender's auto-smooth shading on the selected meshes."""
    select_mesh_objects(objects)
    bpy.ops.object.shade_auto_smooth()


def import_enclosure(filepath):
    """Import the generated enclosure STL in print orientation, scaled to meters."""
    existing = set(bpy.data.objects)
    bpy.ops.wm.stl_import(filepath=str(filepath))
    imported = [obj for obj in bpy.data.objects if obj not in existing]
    meshes = get_mesh_objects(imported)
    if not meshes:
        raise RuntimeError("STL import did not create any mesh objects.")

    for obj in meshes:
        obj.scale = (MODEL_SCALE_METERS, MODEL_SCALE_METERS, MODEL_SCALE_METERS)
    bpy.context.view_layer.update()

    root = parent_objects_to_empty(meshes, "EnclosurePrintRoot", recenter=True)
    return root, meshes


def create_display_root(objects):
    """Create a display root that rotates the print-oriented assembly upright."""
    root = bpy.data.objects.new("TurnaroundAssemblyRoot", None)
    bpy.context.collection.objects.link(root)
    for obj in objects:
        obj.parent = root
        obj.matrix_parent_inverse = root.matrix_world.inverted()
    root.rotation_euler = tuple(math.radians(value) for value in TURNAROUND_DISPLAY_ROTATION_DEG)
    bpy.context.view_layer.update()
    return root


def fit_mac_studio_asset(root, mac_objects):
    """Find the authoritative asset orientation and return the uniform fit scale."""
    best_rotation = None
    best_fit_scale = None
    best_error = None

    for rotation_deg in MAC_STUDIO_CANDIDATE_ROTATIONS_DEG:
        root.rotation_euler = tuple(math.radians(value) for value in rotation_deg)
        root.scale = (1.0, 1.0, 1.0)
        bpy.context.view_layer.update()

        mins, maxs = get_world_bbox(mac_objects)
        dims = maxs - mins
        fit_scale = MAC_STUDIO_TARGET_DIMS_M.dot(dims) / max(dims.dot(dims), 1e-12)
        residual = MAC_STUDIO_TARGET_DIMS_M - (dims * fit_scale)
        error = residual.length

        if best_error is None or error < best_error:
            best_rotation = rotation_deg
            best_fit_scale = fit_scale
            best_error = error

    root.rotation_euler = tuple(math.radians(value) for value in best_rotation)
    root.scale = (best_fit_scale, best_fit_scale, best_fit_scale)
    bpy.context.view_layer.update()


def create_fallback_mac_material():
    """Create a simple aluminum-like material if the USDZ import lacks materials."""
    mat = bpy.data.materials.new(name="Mac_Studio_Material")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (0, 0)
    bsdf.inputs["Base Color"].default_value = (0.72, 0.74, 0.77, 1.0)
    bsdf.inputs["Metallic"].default_value = 0.15
    bsdf.inputs["Roughness"].default_value = 0.28
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.5
    elif "Specular" in bsdf.inputs:
        bsdf.inputs["Specular"].default_value = 0.5

    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (300, 0)
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    return mat


def imported_mac_has_materials(mac_objects):
    """Return True when the imported USDZ already provides usable materials."""
    return any(
        slot.material is not None
        for obj in mac_objects
        for slot in obj.material_slots
    )


def import_mac_studio(filepath, enclosure_meshes):
    """Import, orient, scale, and position the Mac Studio in print orientation."""
    existing = set(bpy.data.objects)
    bpy.ops.wm.usd_import(filepath=str(filepath))
    imported = [obj for obj in bpy.data.objects if obj not in existing]
    mac_objects = get_mesh_objects(imported)
    if not mac_objects:
        raise RuntimeError("USD import did not create any mesh objects.")

    root = parent_objects_to_empty(mac_objects, "MacStudioPrintRoot", recenter=True)
    fit_mac_studio_asset(root, mac_objects)

    enclosure_center = get_bbox_center(enclosure_meshes)
    mac_center = get_bbox_center(mac_objects)
    root.location += enclosure_center - mac_center
    root.location.z += BODY_CENTER_VERTICAL_OFFSET_M
    bpy.context.view_layer.update()

    used_imported_materials = imported_mac_has_materials(mac_objects)
    if not used_imported_materials:
        mac_material = create_fallback_mac_material()
        for obj in mac_objects:
            obj.data.materials.clear()
            obj.data.materials.append(mac_material)

    return root, mac_objects, used_imported_materials


def create_material():
    """Create a clean plastic-like material for the enclosure."""
    mat = bpy.data.materials.new(name="Enclosure_Material")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (0, 0)
    bsdf.inputs["Base Color"].default_value = (0.85, 0.85, 0.85, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.35
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.5
    elif "Specular" in bsdf.inputs:
        bsdf.inputs["Specular"].default_value = 0.5

    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (300, 0)
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    return mat


def setup_lighting(target_obj=None, orthographic_front=False):
    """Three-point lighting with an optional front fill for orthographic renders."""
    key_data = bpy.data.lights.new(name="Key", type="AREA")
    key_data.energy = 200
    key_data.size = 2.0
    key_data.color = (1.0, 0.98, 0.95)
    key_obj = bpy.data.objects.new("Key", key_data)
    bpy.context.collection.objects.link(key_obj)
    key_obj.location = (2.0, -2.0, 3.0)
    key_obj.rotation_euler = (math.radians(45), 0, math.radians(45))

    fill_data = bpy.data.lights.new(name="Fill", type="AREA")
    fill_data.energy = 80
    fill_data.size = 3.0
    fill_data.color = (0.9, 0.93, 1.0)
    fill_obj = bpy.data.objects.new("Fill", fill_data)
    bpy.context.collection.objects.link(fill_obj)
    fill_obj.location = (-2.5, -1.0, 2.0)
    fill_obj.rotation_euler = (math.radians(50), 0, math.radians(-60))

    rim_data = bpy.data.lights.new(name="Rim", type="AREA")
    rim_data.energy = 120
    rim_data.size = 1.5
    rim_obj = bpy.data.objects.new("Rim", rim_data)
    bpy.context.collection.objects.link(rim_obj)
    rim_obj.location = (0.5, 3.0, 2.5)
    rim_obj.rotation_euler = (math.radians(-45), 0, math.radians(180))

    world = bpy.data.worlds.new("TurnaroundWorld")
    bpy.context.scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes["Background"]
    background.inputs["Color"].default_value = (0.05, 0.05, 0.06, 1.0)
    background.inputs["Strength"].default_value = 0.3

    if orthographic_front:
        front_data = bpy.data.lights.new(name="FrontFill", type="AREA")
        front_data.energy = 90
        front_data.size = 2.2
        front_data.color = (1.0, 0.98, 0.95)
        front_obj = bpy.data.objects.new("FrontFill", front_data)
        bpy.context.collection.objects.link(front_obj)
        front_obj.location = (-1.6, 1.8, 1.35)
        if target_obj is not None:
            track = front_obj.constraints.new(type="TRACK_TO")
            track.target = target_obj
            track.track_axis = "TRACK_NEGATIVE_Z"
            track.up_axis = "UP_Y"


def setup_camera(target_obj, render_objects, bounding_radius, total_frames, orthographic_front=False):
    """Create either the turnaround camera or a static orthographic front camera."""
    if orthographic_front:
        mins, maxs = get_world_bbox(render_objects)
        center = (mins + maxs) / 2.0
        width = maxs.x - mins.x
        height = maxs.z - mins.z
        depth = maxs.y - mins.y

        cam_data = bpy.data.cameras.new("FrontOrthoCamera")
        cam_data.type = "ORTHO"
        cam_data.ortho_scale = max(width, height) * ORTHO_FRONT_MARGIN
        cam_data.clip_start = 0.01
        cam_data.clip_end = 100.0
        cam_obj = bpy.data.objects.new("FrontOrthoCamera", cam_data)
        bpy.context.collection.objects.link(cam_obj)
        cam_obj.location = (center.x, maxs.y + max(depth * 2.0, 0.5), center.z)

        track = cam_obj.constraints.new(type="TRACK_TO")
        track.target = target_obj
        track.track_axis = "TRACK_NEGATIVE_Z"
        track.up_axis = "UP_Y"

        bpy.context.scene.camera = cam_obj
        return cam_obj

    elevation = math.radians(CAMERA_ELEVATION_DEG)
    distance = bounding_radius * CAMERA_DISTANCE_FACTOR

    cam_data = bpy.data.cameras.new("TurnaroundCamera")
    cam_data.lens = 80
    cam_data.clip_start = 0.01
    cam_data.clip_end = 100.0
    cam_obj = bpy.data.objects.new("TurnaroundCamera", cam_data)
    bpy.context.collection.objects.link(cam_obj)

    track = cam_obj.constraints.new(type="TRACK_TO")
    track.target = target_obj
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"

    pivot = bpy.data.objects.new("CameraPivot", None)
    pivot.location = target_obj.location.copy()
    bpy.context.collection.objects.link(pivot)
    cam_obj.parent = pivot
    cam_obj.matrix_parent_inverse = pivot.matrix_world.inverted()

    cam_x = distance * math.cos(elevation)
    cam_z = distance * math.sin(elevation)
    cam_obj.location = (cam_x, 0, cam_z)

    pivot.rotation_euler = (0, 0, 0)
    pivot.keyframe_insert(data_path="rotation_euler", frame=1)
    pivot.rotation_euler = (0, 0, math.radians(360))
    pivot.keyframe_insert(data_path="rotation_euler", frame=total_frames + 1)

    if pivot.animation_data and pivot.animation_data.action:
        action = pivot.animation_data.action
        for layer in action.layers:
            for strip in layer.strips:
                for channelbag in strip.channelbags:
                    for fcurve in channelbag.fcurves:
                        for keyframe in fcurve.keyframe_points:
                            keyframe.interpolation = "LINEAR"

    bpy.context.scene.camera = cam_obj
    return cam_obj


def setup_render(settings):
    """Configure render settings and return the timeline frame count."""
    scene = bpy.context.scene
    total_frames = settings["fps"] * settings["duration_seconds"]
    scene.frame_start = 1
    scene.frame_end = total_frames
    scene.render.fps = settings["fps"]

    scene.render.resolution_x = settings["resolution_x"]
    scene.render.resolution_y = settings["resolution_y"]
    scene.render.resolution_percentage = 100

    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = settings["samples"]

    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.compression = 15

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(OUTPUT_DIR / "frame_")
    scene.render.film_transparent = False
    return total_frames


def still_output_path(render_mode, frame_number):
    """Return the output path for a single rendered frame."""
    return OUTPUT_DIR / f"turnaround_{render_mode}_frame_{frame_number:04d}.png"


def add_ground_plane(render_objects):
    """Add a subtle ground plane beneath the assembly."""
    bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, 0))
    plane = bpy.context.active_object
    plane.name = "GroundPlane"

    min_z = min(world_co.z for world_co in get_world_vertices(render_objects))
    plane.location.z = min_z

    mat = bpy.data.materials.new(name="Ground_Material")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.02, 0.02, 0.025, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.8
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.1
    elif "Specular" in bsdf.inputs:
        bsdf.inputs["Specular"].default_value = 0.1

    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (300, 0)
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

    plane.data.materials.append(mat)
    return plane


def main():
    args = parse_args()
    render_mode = args.render_mode
    render_settings = RENDER_PRESETS[render_mode]

    if not MODEL_PATH.is_file():
        print(f"ERROR: Model not found at {MODEL_PATH}")
        sys.exit(1)
    if args.include_mac_studio and not MAC_STUDIO_PATH.is_file():
        print(f"ERROR: Mac Studio model not found at {MAC_STUDIO_PATH}")
        sys.exit(1)

    print(f"Render preset: {render_mode}")
    print(f"Importing enclosure from {MODEL_PATH}")
    clear_scene()

    enclosure_root, enclosure_meshes = import_enclosure(MODEL_PATH)
    shade_auto_smooth(enclosure_meshes)
    enclosure_material = create_material()
    for obj in enclosure_meshes:
        obj.data.materials.clear()
        obj.data.materials.append(enclosure_material)
    print(f"Imported enclosure — {sum(len(obj.data.vertices) for obj in enclosure_meshes)} verts")

    render_objects = list(enclosure_meshes)
    display_children = [enclosure_root]

    if args.include_mac_studio:
        print(
            "Importing Mac Studio from "
            f"{MAC_STUDIO_PATH} using placement from main.py"
        )
        mac_root, mac_meshes, used_imported_materials = import_mac_studio(
            MAC_STUDIO_PATH,
            enclosure_meshes,
        )
        display_children.append(mac_root)
        render_objects.extend(mac_meshes)
        print(f"Imported Mac Studio — {len(mac_meshes)} mesh objects")
        if used_imported_materials:
            print("Using the real USDZ materials and textures for the Mac Studio.")
        else:
            print("USDZ import did not provide materials; using the fallback Mac shader.")

    create_display_root(display_children)

    target = bpy.data.objects.new("CameraTarget", None)
    target.location = get_bbox_center(render_objects)
    bpy.context.collection.objects.link(target)

    radius = get_bounding_radius(render_objects)
    print(f"Bounding radius: {radius:.3f} m")

    setup_lighting(target, orthographic_front=args.orthographic_front)
    total_frames = render_settings["fps"] * render_settings["duration_seconds"]
    setup_camera(
        target,
        render_objects,
        radius,
        total_frames,
        orthographic_front=args.orthographic_front,
    )
    add_ground_plane(render_objects)
    total_frames = setup_render(render_settings)

    if args.frame is not None:
        frame_number = args.frame
        if frame_number < 1 or frame_number > total_frames:
            print(
                f"ERROR: Frame {frame_number} is outside the valid range "
                f"1-{total_frames} for the {render_mode} preset."
            )
            sys.exit(1)

        scene = bpy.context.scene
        scene.frame_set(frame_number)
        still_path = still_output_path(render_mode, frame_number)
        scene.render.filepath = str(still_path)

        print(
            f"Rendering still frame {frame_number}/{total_frames} at "
            f"{render_settings['resolution_x']}x{render_settings['resolution_y']} "
            f"with {render_settings['samples']} samples ..."
        )
        bpy.ops.render.render(write_still=True)
        print(f"Done! Output saved to: {still_path}")
        return

    print(
        "Rendering "
        f"{total_frames} frames at "
        f"{render_settings['resolution_x']}x{render_settings['resolution_y']} "
        f"with {render_settings['samples']} samples ..."
    )
    bpy.ops.render.render(animation=True)

    frame_pattern = str(OUTPUT_DIR / "frame_%04d.png")
    mp4_path = OUTPUT_DIR / render_settings["output_name"]
    cmd = [
        "ffmpeg",
        "-y",
        "-framerate",
        str(render_settings["fps"]),
        "-start_number",
        "1",
        "-i",
        frame_pattern,
        "-c:v",
        "libx264",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(mp4_path),
    ]
    print(f"Encoding MP4: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)

    for frame_path in OUTPUT_DIR.glob("frame_*.png"):
        frame_path.unlink()

    print(f"Done! Output saved to: {mp4_path}")


if __name__ == "__main__":
    main()
