"""
Generate a 360-degree turnaround video of the Mac Studio enclosure.

Usage:
  /Applications/Blender.app/Contents/MacOS/Blender --background --python turnaround.py
  /Applications/Blender.app/Contents/MacOS/Blender --background --python turnaround.py -- --final
  /Applications/Blender.app/Contents/MacOS/Blender --background --python turnaround.py -- --frame
  /Applications/Blender.app/Contents/MacOS/Blender --background --python turnaround.py -- --include-mac-studio
"""

import argparse
import bpy
import math
import os
import sys
from mathutils import Vector

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(SCRIPT_DIR, "mac_studio_enclosure.stl")
MAC_STUDIO_PATH = os.path.join(SCRIPT_DIR, "mac-studio.usdz")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "turnaround_output")

ENCLOSURE_WALL_THICKNESS = 0.004
SIDE_CLEARANCE = 0.0055
TOP_BOTTOM_CLEARANCE = 0.0025
MAC_STUDIO_TARGET_DIMS = Vector((0.196726, 0.197478, 0.095133))
# Lock the USDZ asset to an explicit orientation so asymmetric enclosure features
# stay on the intended rendered side. This preserves the current "front ports to
# the opening, top surface upright" presentation without relying on ambiguous
# bounding-box fitting across a nearly square footprint.
MAC_STUDIO_ASSET_ROTATION_DEG = (90, 0, 180)

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

# Camera orbit settings
CAMERA_ELEVATION_DEG = 25  # Angle above the horizon
CAMERA_DISTANCE_FACTOR = 6.0  # Multiplier on model bounding radius
DEFAULT_STILL_FRAME = 25
ORTHO_FRONT_MARGIN = 1.15

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def clear_scene():
    """Remove all default objects."""
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    # Remove orphan data
    for block in bpy.data.meshes:
        if block.users == 0:
            bpy.data.meshes.remove(block)
    for block in bpy.data.materials:
        if block.users == 0:
            bpy.data.materials.remove(block)
    for block in bpy.data.cameras:
        if block.users == 0:
            bpy.data.cameras.remove(block)
    for block in bpy.data.lights:
        if block.users == 0:
            bpy.data.lights.remove(block)


def parse_args():
    """Parse script arguments passed after Blender's `--` separator."""
    argv = sys.argv
    script_argv = argv[argv.index("--") + 1:] if "--" in argv else []

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


def import_model(filepath):
    """Import the STL model and return the imported object."""
    bpy.ops.wm.stl_import(filepath=filepath)
    obj = bpy.context.selected_objects[0]
    # STL is in millimeters — scale to meters
    obj.scale = (0.001, 0.001, 0.001)
    bpy.ops.object.transform_apply(scale=True)
    # STL is stored in print orientation; rotate into the normal
    # upright Mac Studio orientation for the turnaround render.
    import math as _math
    obj.rotation_euler = (_math.radians(180), 0, 0)
    bpy.ops.object.transform_apply(rotation=True)
    # Center the object at the origin
    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
    obj.location = (0, 0, 0)
    return obj


def get_mesh_objects(objects):
    """Return only mesh objects from an iterable."""
    return [obj for obj in objects if obj.type == "MESH"]


def get_world_vertices(objects):
    """Return all world-space vertices for the given mesh objects."""
    verts = []
    for obj in get_mesh_objects(objects):
        verts.extend(obj.matrix_world @ v.co for v in obj.data.vertices)
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
    return max((v - center).length for v in verts)


def parent_objects_to_empty(objects, name):
    """Parent imported objects to a single empty while preserving transforms."""
    center = get_bbox_center(objects)
    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    root.location = center
    for obj in objects:
        obj.parent = root
        obj.matrix_parent_inverse = root.matrix_world.inverted()
    root.location = (0, 0, 0)
    bpy.context.view_layer.update()
    return root


def orient_mac_studio_asset(root, mac_objects):
    """Apply a deterministic USDZ orientation and return the fitted uniform scale."""
    root.rotation_euler = tuple(math.radians(v) for v in MAC_STUDIO_ASSET_ROTATION_DEG)
    bpy.context.view_layer.update()

    mins, maxs = get_world_bbox(mac_objects)
    dims = maxs - mins
    scale = MAC_STUDIO_TARGET_DIMS.dot(dims) / max(dims.dot(dims), 1e-12)
    return scale


def create_mac_material():
    """Create a simple aluminum-like material for the Mac Studio."""
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

    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (300, 0)
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    return mat


def import_mac_studio(filepath, enclosure_obj):
    """Import, orient, scale, and position the Mac Studio and enclosure together."""
    existing_objects = set(bpy.data.objects)
    bpy.ops.wm.usd_import(filepath=filepath)
    imported = [obj for obj in bpy.data.objects if obj not in existing_objects]
    mac_objects = get_mesh_objects(imported)
    if not mac_objects:
        raise RuntimeError("USD import did not create any mesh objects.")

    root = parent_objects_to_empty(mac_objects, "MacStudioRoot")
    scale = orient_mac_studio_asset(root, mac_objects)
    root.scale = (scale, scale, scale)
    bpy.context.view_layer.update()

    enclosure_mins, enclosure_maxs = get_world_bbox([enclosure_obj])
    mac_mins, mac_maxs = get_world_bbox(mac_objects)
    mac_dims = mac_maxs - mac_mins
    enclosure_center = (enclosure_mins + enclosure_maxs) / 2.0
    front_face_y = enclosure_maxs.y
    mac_center_y = front_face_y - (ENCLOSURE_WALL_THICKNESS + SIDE_CLEARANCE + mac_dims.y / 2.0)

    root.location = (enclosure_center.x, mac_center_y, -mac_mins.z)
    bpy.context.view_layer.update()

    enclosure_mins, enclosure_maxs = get_world_bbox([enclosure_obj])
    desired_enclosure_min_z = TOP_BOTTOM_CLEARANCE
    enclosure_obj.location.z += desired_enclosure_min_z - enclosure_mins.z
    bpy.context.view_layer.update()

    mac_material = create_mac_material()
    for obj in mac_objects:
        obj.data.materials.clear()
        obj.data.materials.append(mac_material)

    return root, mac_objects


def create_material():
    """Create a clean plastic-like material for the enclosure."""
    mat = bpy.data.materials.new(name="Enclosure_Material")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    # Clear defaults
    nodes.clear()

    # Principled BSDF
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (0, 0)
    bsdf.inputs["Base Color"].default_value = (0.85, 0.85, 0.85, 1.0)  # Light grey
    bsdf.inputs["Roughness"].default_value = 0.35
    bsdf.inputs["Specular IOR Level"].default_value = 0.5

    # Output
    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (300, 0)
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

    return mat


def setup_lighting(target_obj=None, orthographic_front=False):
    """Three-point lighting with an optional front fill for orthographic renders."""
    # Key light — area light, upper-right
    key_data = bpy.data.lights.new(name="Key", type="AREA")
    key_data.energy = 200
    key_data.size = 2.0
    key_data.color = (1.0, 0.98, 0.95)
    key_obj = bpy.data.objects.new("Key", key_data)
    bpy.context.collection.objects.link(key_obj)
    key_obj.location = (2.0, -2.0, 3.0)
    key_obj.rotation_euler = (math.radians(45), 0, math.radians(45))

    # Fill light — softer, opposite side
    fill_data = bpy.data.lights.new(name="Fill", type="AREA")
    fill_data.energy = 80
    fill_data.size = 3.0
    fill_data.color = (0.9, 0.93, 1.0)
    fill_obj = bpy.data.objects.new("Fill", fill_data)
    bpy.context.collection.objects.link(fill_obj)
    fill_obj.location = (-2.5, -1.0, 2.0)
    fill_obj.rotation_euler = (math.radians(50), 0, math.radians(-60))

    # Rim / back light
    rim_data = bpy.data.lights.new(name="Rim", type="AREA")
    rim_data.energy = 120
    rim_data.size = 1.5
    rim_obj = bpy.data.objects.new("Rim", rim_data)
    bpy.context.collection.objects.link(rim_obj)
    rim_obj.location = (0.5, 3.0, 2.5)
    rim_obj.rotation_euler = (math.radians(-45), 0, math.radians(180))

    # Subtle world environment for ambient fill
    world = bpy.data.worlds.new("TurnaroundWorld")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.05, 0.05, 0.06, 1.0)
    bg.inputs["Strength"].default_value = 0.3

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

    # Default turnaround camera: perspective camera parented to a rotating pivot.
    elevation = math.radians(CAMERA_ELEVATION_DEG)
    distance = bounding_radius * CAMERA_DISTANCE_FACTOR

    # Camera
    cam_data = bpy.data.cameras.new("TurnaroundCamera")
    cam_data.lens = 80  # Slightly telephoto to reduce distortion
    cam_data.clip_start = 0.01
    cam_data.clip_end = 100.0
    cam_obj = bpy.data.objects.new("TurnaroundCamera", cam_data)
    bpy.context.collection.objects.link(cam_obj)

    # Position camera
    cam_x = distance * math.cos(elevation)
    cam_z = distance * math.sin(elevation)
    cam_obj.location = (cam_x, 0, cam_z)

    # Track-To constraint keeps camera pointed at center
    track = cam_obj.constraints.new(type="TRACK_TO")
    track.target = target_obj
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"

    # Empty at origin — camera orbits around this
    pivot = bpy.data.objects.new("CameraPivot", None)
    pivot.location = (0, 0, 0)
    bpy.context.collection.objects.link(pivot)

    cam_obj.parent = pivot

    # Animate pivot rotation: 0 → 360 degrees over the timeline
    pivot.rotation_euler = (0, 0, 0)
    pivot.keyframe_insert(data_path="rotation_euler", frame=1)
    pivot.rotation_euler = (0, 0, math.radians(360))
    pivot.keyframe_insert(data_path="rotation_euler", frame=total_frames + 1)

    # Linear interpolation so speed is constant (Blender 5 layered action API)
    if pivot.animation_data and pivot.animation_data.action:
        action = pivot.animation_data.action
        for layer in action.layers:
            for strip in layer.strips:
                for channelbag in strip.channelbags:
                    for fcurve in channelbag.fcurves:
                        for kf in fcurve.keyframe_points:
                            kf.interpolation = "LINEAR"

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

    # Use EEVEE
    scene.render.engine = "BLENDER_EEVEE"
    eevee = scene.eevee
    eevee.taa_render_samples = settings["samples"]
    print("Render engine: EEVEE")

    # Render to PNG frames (ffmpeg encodes to MP4 after)
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.compression = 15

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    scene.render.filepath = os.path.join(OUTPUT_DIR, "frame_")

    scene.render.film_transparent = False
    return total_frames


def still_output_path(render_mode, frame_number):
    """Return the output path for a single rendered frame."""
    return os.path.join(
        OUTPUT_DIR,
        f"turnaround_{render_mode}_frame_{frame_number:04d}.png",
    )


def add_ground_plane(render_objects):
    """Add a subtle ground shadow-catcher plane."""
    bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, 0))
    plane = bpy.context.active_object
    plane.name = "GroundPlane"

    # Find the lowest point of any mesh object to position the plane
    min_z = 0
    for world_co in get_world_vertices(render_objects):
        min_z = min(min_z, world_co.z)

    plane.location.z = min_z

    # Shadow catcher material — dark surface that catches shadows
    mat = bpy.data.materials.new(name="Ground_Material")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.02, 0.02, 0.025, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.8
    bsdf.inputs["Specular IOR Level"].default_value = 0.1

    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (300, 0)
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

    plane.data.materials.append(mat)
    return plane


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()
    render_mode = args.render_mode
    render_settings = RENDER_PRESETS[render_mode]

    if not os.path.isfile(MODEL_PATH):
        print(f"ERROR: Model not found at {MODEL_PATH}")
        sys.exit(1)
    if args.include_mac_studio and not os.path.isfile(MAC_STUDIO_PATH):
        print(f"ERROR: Mac Studio model not found at {MAC_STUDIO_PATH}")
        sys.exit(1)

    print(f"Render preset: {render_mode}")
    print(f"Importing model from {MODEL_PATH}")
    clear_scene()

    # Import
    obj = import_model(MODEL_PATH)
    print(f"Imported: {obj.name}  —  {len(obj.data.vertices)} verts")
    render_objects = [obj]

    # Auto-smooth by angle — only smooths faces within 30 degrees of each other,
    # keeping hard edges sharp and eliminating vertex-shadow artifacts
    bpy.ops.object.shade_auto_smooth()

    # Apply material
    mat = create_material()
    obj.data.materials.clear()
    obj.data.materials.append(mat)

    if args.include_mac_studio:
        print(f"Importing Mac Studio from {MAC_STUDIO_PATH}")
        _, mac_objects = import_mac_studio(MAC_STUDIO_PATH, obj)
        render_objects.extend(mac_objects)
        print(f"Imported Mac Studio — {len(mac_objects)} mesh objects")

    # Create an empty at the assembly center for tracking
    target = bpy.data.objects.new("CameraTarget", None)
    target.location = get_bbox_center(render_objects)
    bpy.context.collection.objects.link(target)

    # Setup scene
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
        scene.render.filepath = still_path

        print(
            f"Rendering still frame {frame_number}/{total_frames} at "
            f"{render_settings['resolution_x']}x{render_settings['resolution_y']} "
            f"with {render_settings['samples']} samples ..."
        )
        bpy.ops.render.render(write_still=True)
        print(f"Done! Output saved to: {still_path}")
        return

    # Render frames
    print(
        "Rendering "
        f"{total_frames} frames at "
        f"{render_settings['resolution_x']}x{render_settings['resolution_y']} "
        f"with {render_settings['samples']} samples ..."
    )
    bpy.ops.render.render(animation=True)

    # Encode to MP4 with ffmpeg
    import subprocess
    frame_pattern = os.path.join(OUTPUT_DIR, "frame_%04d.png")
    mp4_path = os.path.join(OUTPUT_DIR, render_settings["output_name"])
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(render_settings["fps"]),
        "-start_number", "1",
        "-i", frame_pattern,
        "-c:v", "libx264",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        mp4_path,
    ]
    print(f"Encoding MP4: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)

    # Clean up PNG frames
    for f in os.listdir(OUTPUT_DIR):
        if f.startswith("frame_") and f.endswith(".png"):
            os.remove(os.path.join(OUTPUT_DIR, f))

    print(f"Done! Output saved to: {mp4_path}")


if __name__ == "__main__":
    main()
