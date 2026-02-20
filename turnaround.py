"""
Generate a 360-degree turnaround video of the Mac Studio enclosure.

Usage:
  /Applications/Blender.app/Contents/MacOS/Blender --background --python turnaround.py
"""

import bpy
import math
import os
import sys

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(SCRIPT_DIR, "mac_studio_enclosure.stl")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "turnaround_output")

RESOLUTION_X = 1920
RESOLUTION_Y = 1080
FPS = 30
DURATION_SECONDS = 6
TOTAL_FRAMES = FPS * DURATION_SECONDS
SAMPLES = 128  # Cycles render samples

# Camera orbit settings
CAMERA_ELEVATION_DEG = 25  # Angle above the horizon
CAMERA_DISTANCE_FACTOR = 6.0  # Multiplier on model bounding radius

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


def import_model(filepath):
    """Import the STL model and return the imported object."""
    bpy.ops.wm.stl_import(filepath=filepath)
    obj = bpy.context.selected_objects[0]
    # STL is in millimeters — scale to meters
    obj.scale = (0.001, 0.001, 0.001)
    bpy.ops.object.transform_apply(scale=True)
    # Rotate so the enclosure top (short Y axis) faces up (Z)
    import math as _math
    obj.rotation_euler = (_math.radians(90), 0, 0)
    bpy.ops.object.transform_apply(rotation=True)
    # Center the object at the origin
    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
    obj.location = (0, 0, 0)
    return obj


def get_bounding_radius(obj):
    """Return the radius of the bounding sphere of the object."""
    bbox = [obj.matrix_world @ v.co for v in obj.data.vertices]
    from mathutils import Vector
    center = sum(bbox, Vector()) / len(bbox)
    return max((v - center).length for v in bbox)


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


def setup_lighting():
    """Three-point lighting with a soft environment."""
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


def setup_camera(target_obj, bounding_radius):
    """Create camera and parent it to an empty that rotates 360 degrees."""
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
    pivot.keyframe_insert(data_path="rotation_euler", frame=TOTAL_FRAMES + 1)

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


def setup_render():
    """Configure render settings for Cycles with MP4 output."""
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = TOTAL_FRAMES
    scene.render.fps = FPS

    scene.render.resolution_x = RESOLUTION_X
    scene.render.resolution_y = RESOLUTION_Y
    scene.render.resolution_percentage = 100

    # Use EEVEE
    scene.render.engine = "BLENDER_EEVEE"
    eevee = scene.eevee
    eevee.taa_render_samples = SAMPLES
    print("Render engine: EEVEE")

    # Render to PNG frames (ffmpeg encodes to MP4 after)
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.compression = 15

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    scene.render.filepath = os.path.join(OUTPUT_DIR, "frame_")

    scene.render.film_transparent = False


def add_ground_plane():
    """Add a subtle ground shadow-catcher plane."""
    bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, 0))
    plane = bpy.context.active_object
    plane.name = "GroundPlane"

    # Find the lowest point of any mesh object to position the plane
    min_z = 0
    for obj in bpy.data.objects:
        if obj.type == "MESH" and obj.name != "GroundPlane":
            for v in obj.data.vertices:
                world_co = obj.matrix_world @ v.co
                min_z = min(min_z, world_co.z)

    plane.location.z = min_z - 0.001

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
    if not os.path.isfile(MODEL_PATH):
        print(f"ERROR: Model not found at {MODEL_PATH}")
        sys.exit(1)

    print(f"Importing model from {MODEL_PATH}")
    clear_scene()

    # Import
    obj = import_model(MODEL_PATH)
    print(f"Imported: {obj.name}  —  {len(obj.data.vertices)} verts")

    # Auto-smooth by angle — only smooths faces within 30 degrees of each other,
    # keeping hard edges sharp and eliminating vertex-shadow artifacts
    bpy.ops.object.shade_auto_smooth()

    # Apply material
    mat = create_material()
    obj.data.materials.clear()
    obj.data.materials.append(mat)

    # Create an empty at origin for tracking
    target = bpy.data.objects.new("CameraTarget", None)
    target.location = (0, 0, 0)
    bpy.context.collection.objects.link(target)

    # Setup scene
    radius = get_bounding_radius(obj)
    print(f"Bounding radius: {radius:.3f} m")

    setup_lighting()
    setup_camera(target, radius)
    add_ground_plane()
    setup_render()

    # Render frames
    print(f"Rendering {TOTAL_FRAMES} frames at {RESOLUTION_X}x{RESOLUTION_Y} ...")
    bpy.ops.render.render(animation=True)

    # Encode to MP4 with ffmpeg
    import subprocess
    frame_pattern = os.path.join(OUTPUT_DIR, "frame_%04d.png")
    mp4_path = os.path.join(OUTPUT_DIR, "turnaround.mp4")
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(FPS),
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
