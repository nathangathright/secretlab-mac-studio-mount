// Mac Studio Under-Desk Enclosure
// Parametric design — all dimensions derived from Mac Studio USDZ model measurements

// ── Mac Studio Measurements (from USDZ vertex analysis) ──────────────
body_w         = 197;    // A: body width (square footprint, mm)
body_h         = 95;     // B: body height (mm)
corner_r       = 30.4;   // C: body corner radius (mm, fitted from USDZ vertices)
base_circle_d  = 179.2;  // G: bottom vent ring diameter (mm)
base_protrusion = 8;     // H: base ring depth below body (mm)

// ── Clearances ───────────────────────────────────────────────────────
side_clearance = 5.5;    // clearance per side (mm)
tb_clearance   = 2.5;    // clearance top and bottom (mm)

// ── Wall ─────────────────────────────────────────────────────────────
wall = 4;                // wall thickness (mm)

// ── Computed Enclosure Dimensions ────────────────────────────────────
enc_w  = body_w + 2 * side_clearance;          // 208 mm
enc_d  = body_w + 2 * side_clearance;          // 208 mm (square footprint)
enc_h  = body_h + 2 * tb_clearance;            // 100 mm
enc_cr = corner_r + side_clearance;            // 35.9 mm outer corner radius
inner_cr = enc_cr - wall;                      // 31.9 mm inner corner radius

// ── Front Cutout ───────────────────────────────────────────────────────
// Keep the opening centered, but widen it enough that the earlier
// lower-corner USB-C relief becomes unnecessary.
front_w_margin  = 5;     // margin inward from start of flat face (mm)
front_h_margin  = 15;    // margin from top/bottom enclosure edge (mm)
front_cutout_extra_w = 12;  // centered width increase to absorb the former one-sided relief
front_cutout_w  = enc_w - 2 * enc_cr - 2 * front_w_margin + front_cutout_extra_w;  // ~138.2 mm
front_cutout_h  = enc_h - 2 * front_h_margin;                // 70 mm
front_cutout_cr = 3;     // tighter radius preserves width lower in the port band
front_cutout_chamfer = 1.5;  // front-face chamfer depth/width around the opening (mm)

// ── Top Cutout ───────────────────────────────────────────────────────
top_cutout_side = front_cutout_w;  // keep the top opening matched to the front opening width
top_cutout_cr   = front_cutout_cr;  // use the same corner radius as the front opening
top_cutout_chamfer = front_cutout_chamfer;  // mirror the front opening chamfer

// ── Rear Tip Outer Profile ───────────────────────────────────────────
rear_tip_outer_r = 4;    // target rear tip round-over radius (mm)
rear_tip_leg_angle = 126.56;  // interior angle of each trapezoid leg (deg)

// ── Screw Slot Parameters ────────────────────────────────────────────
slot_w = 5;              // slot width — M5 bolt clearance (mm)
slot_l = 10;             // slot length — adjustment travel (mm)
slot_rect_w = 50;        // slot rectangle width along depth (mm)
slot_rect_h = 30;        // slot rectangle height (mm)
slot_top_offset = 14;    // top edge of rectangle from enclosure top (mm)

// Slot center positions (from top-front corner of side face)
slot_depth_center = enc_d / 2;                 // centered along depth
slot_y_top  = enc_h / 2 - slot_top_offset;     // top row Y
slot_y_bot  = slot_y_top - slot_rect_h;         // bottom row Y
slot_z_front = slot_depth_center - slot_rect_w / 2;  // front column Z
slot_z_back  = slot_depth_center + slot_rect_w / 2;  // back column Z

// Slot convergence angle: atan2(half_rect_w, half_rect_h)
slot_angle = atan2(slot_rect_w / 2, slot_rect_h / 2);  // ~59.0 degrees

// ── Resolution ───────────────────────────────────────────────────────
$fn = 80;

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

// ═══════════════════════════════════════════════════════════════════════
// Enclosure Components
// ═══════════════════════════════════════════════════════════════════════

// Rounded box: 4 rounded edges run along Y (height axis), at corners
// of the XZ (width x depth) footprint. Top/bottom faces are flat.
// w = width (X), d = depth (Z from 0 to d), h = height (Y centered), cr = corner radius
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
        // Outer body — rounded square footprint, extruded to height
        rounded_box(enc_w, enc_d, enc_h, enc_cr);

        // Inner cavity — walls on front/left/right/top/bottom, open back
        // Front inner cylinders at Z = wall + inner_cr (preserves front wall)
        // Back inner cylinders extend past Z = enc_d (opens the back)
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

    // Chamfer only the exterior edge by transitioning from a slightly enlarged
    // outer profile at the front face to the nominal opening inside the wall.
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

    // Chamfer the exterior top-face edge by transitioning from a slightly
    // enlarged profile at the outside surface to the nominal opening inside.
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

// Top face cutout — square hole through the top wall
module top_cutout() {
    translate([0, enc_h / 2 - wall - 1, enc_d / 2])
        rotate([-90, 0, 0])
            union() {
                linear_extrude(wall + 2)
                    top_cutout_profile();

                top_cutout_chamfer_profile();
            }
}

// Exact 2D bottom cutout profile used for both visualization and subtraction.
module bottom_cutout_profile() {
    union() {
        circle(d = base_circle_d);
        translate([0, enc_d / 4])
            square([base_circle_d, enc_d / 2], center = true);
    }
}

// Bottom face cutout — circle + channel to back edge
module bottom_cutout() {
    translate([0, -(enc_h / 2 - wall - 1), enc_d / 2])
        rotate([90, 0, 0])
            linear_extrude(wall + 2)
                bottom_cutout_profile();
}

// 2D rear-tip relief profile. This encodes the same geometry as the previous
// "subtract trapezoid, then add circles back" construction in one subtraction:
// subtract (trapezoid minus circles).
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

// Single screw slot — stadium shape, extruded through wall
module screw_slot(angle) {
    rotate([0, 0, angle])
        linear_extrude(wall + 2, center = true)
            stadium(slot_l, slot_w);
}

// Four slots on one side face
// side_sign: -1 for left, +1 for right
module side_slots(side_sign) {
    x_pos = side_sign * (enc_w / 2 - wall / 2);

    // Each slot: translate to position on face, orient through wall, rotate to angle
    // Slots pass through the side wall (X direction)
    // Slot positions in (Z, Y) on the side face

    slot_positions = [
        [slot_z_front, slot_y_top,   slot_angle],       // top-front
        [slot_z_back,  slot_y_top,  -slot_angle],       // top-back
        [slot_z_front, slot_y_bot,  -slot_angle],       // bottom-front
        [slot_z_back,  slot_y_bot,   slot_angle],       // bottom-back
    ];

    for (s = slot_positions) {
        translate([x_pos, s[1], s[0]])
            rotate([0, 90, 0])
                screw_slot(s[2]);
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
        side_slots(-1);  // left
        side_slots(+1);  // right
    }
}

// Export in the recommended print orientation:
// top face on the bed, vent-ring face up, 100 mm tall in Z.
rotate([-90, 0, 0])
    enclosure_model();
