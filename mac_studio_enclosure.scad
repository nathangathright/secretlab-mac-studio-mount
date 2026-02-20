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

// ── Front Cutout (Option 3: maximum access) ──────────────────────────
// Width margin starts from the flat face (after corner radius), not the outer edge.
// Height margin from the top/bottom edges (which are sharp, not rounded).
front_w_margin  = 5;     // margin inward from start of flat face (mm)
front_h_margin  = 15;    // margin from top/bottom enclosure edge (mm)
front_cutout_w  = enc_w - 2 * enc_cr - 2 * front_w_margin;  // ~126 mm
front_cutout_h  = enc_h - 2 * front_h_margin;                // 70 mm
front_cutout_cr = 12.5;  // cutout corner radius (mm)

// ── Top Cutout ───────────────────────────────────────────────────────
top_cutout_side = 130;   // square side length (mm)
top_cutout_cr   = 12.5;  // corner radius (mm)

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

// Front face cutout — passes through the 4mm front wall
module front_cutout() {
    translate([0, 0, -1])
        linear_extrude(wall + 2)
            rounded_rect(front_cutout_w, front_cutout_h, front_cutout_cr);
}

// Top face cutout — square hole through the top wall
module top_cutout() {
    translate([0, enc_h / 2 - wall - 1, enc_d / 2])
        rotate([-90, 0, 0])
            linear_extrude(wall + 2)
                rounded_rect(top_cutout_side, top_cutout_side, top_cutout_cr);
}

// Bottom face cutout — circle + channel to back edge
module bottom_cutout() {
    translate([0, -(enc_h / 2 - wall - 1), enc_d / 2])
        rotate([90, 0, 0])
            linear_extrude(wall + 2)
                union() {
                    // Vent circle
                    circle(d = base_circle_d);
                    // Channel running from circle center to back edge
                    translate([0, enc_d / 4])
                        square([base_circle_d, enc_d / 2], center = true);
                }
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

difference() {
    shell();
    front_cutout();
    top_cutout();
    bottom_cutout();
    side_slots(-1);  // left
    side_slots(+1);  // right
}
