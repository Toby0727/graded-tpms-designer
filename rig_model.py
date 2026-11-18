# Models the bending fixture shown in the page's 3D view, after a stainless 3-point bend jig (photo reference):
# a box-section base bar with a channel on top and an engraved scale on its front face, two sliding supports (a foot with a
# tongue in the channel, an upright with a through window, a rounded anvil edge on the inner top corner, a knurled thumb
# screw, a wire bail), a stainless loading nose (block with a side cap screw, a V wedge to a rounded edge) under a knurled
# nut and a shank with a flat and a cross hole, and an adapter under the bar (knurled ring, disc, shank with a cross hole).
# Run:  blender -b -P rig_model.py      Output: assets/rig.json
# Part frames (mm, x = span, y = width, z = up):
#   rail      top face at z = 0, centred, 200 long (the page stretches it in x to fit the span)
#   support   the anvil's contact line at z = 0 (the beam's underside), the foot on the rail at z = -50; the upright stands
#             on the -x side of the contact (the page mirrors the part for the support on the +x side)
#   nose      the loading edge at z = 0 (the beam's top face), the block up to z = +56
#   head      knurled nut and shank, from z = 0 (the top of the nose)
#   bar       a spreader for 4-point loading, bottom at z = 0, 100 long (stretched in x)
#   pedestal  under the rail, top at z = 0
import bpy, bmesh, math, os, json, base64, struct

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets')
os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
STEEL, BLACK, POLISH = 0, 1, 2
D2R = math.pi / 180

def sel(ob):
    for o in bpy.context.selected_objects: o.select_set(False)
    ob.select_set(True); bpy.context.view_layer.objects.active = ob

def apply_all(ob):
    sel(ob)
    for m in list(ob.modifiers): bpy.ops.object.modifier_apply(modifier=m.name)

def bevel(ob, w, segs=3, angle=40):
    b = ob.modifiers.new('bv', 'BEVEL'); b.width = w; b.segments = segs; b.limit_method = 'ANGLE'; b.angle_limit = angle * D2R
    apply_all(ob); return ob

def box(sx, sy, sz, loc, bv=0.8, segs=3):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc); ob = bpy.context.object; ob.scale = (sx, sy, sz)
    sel(ob); bpy.ops.object.transform_apply(scale=True)
    return bevel(ob, bv, segs) if bv > 0 else ob

def cyl(r, h, loc, axis='Z', verts=64, bv=0.6, segs=2):
    r0 = {'Z': (0, 0, 0), 'X': (0, math.pi / 2, 0), 'Y': (math.pi / 2, 0, 0)}[axis]
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=h, location=loc, rotation=r0); ob = bpy.context.object
    sel(ob); bpy.ops.object.transform_apply(rotation=True)
    return bevel(ob, bv, segs) if bv > 0 else ob

def knurl(r, h, loc, ridges=60, depth=0.7, bv=0.5):
    """a straight-knurled ring: a prism whose outline alternates between r and r - depth"""
    bm = bmesh.new(); n = ridges * 2
    bot = [bm.verts.new(((r - depth * (i % 2)) * math.cos(2 * math.pi * i / n), (r - depth * (i % 2)) * math.sin(2 * math.pi * i / n), -h / 2)) for i in range(n)]
    f = bm.faces.new(bot); ext = bmesh.ops.extrude_face_region(bm, geom=[f])
    for v in [g for g in ext['geom'] if isinstance(g, bmesh.types.BMVert)]: v.co.z += h
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new('kn'); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new('kn', me); bpy.context.collection.objects.link(ob); ob.location = loc
    sel(ob); bpy.ops.object.transform_apply(location=True)
    return bevel(ob, bv, 1, angle=60) if bv > 0 else ob

def boolean(target, tool, op='DIFFERENCE'):
    m = target.modifiers.new('b', 'BOOLEAN'); m.operation = op; m.object = tool; m.solver = 'EXACT'
    apply_all(target); bpy.data.objects.remove(tool, do_unlink=True); return target

def join(obs):
    obs = [o for o in obs if o is not None]
    for o in obs: apply_all(o)
    for o in bpy.context.selected_objects: o.select_set(False)
    for o in obs: o.select_set(True)
    bpy.context.view_layer.objects.active = obs[0]; bpy.ops.object.join(); return obs[0]

def cap_screw(x, y, z, r=4.0, h=4.2, axis='Z', sign=1):
    """socket-head cap screw with a hex socket; head axis along Z (on a top face) or X (on a side face)"""
    if axis == 'Z':
        head = cyl(r, h, (x, y, z + sign * h / 2), verts=40, bv=0.5); sock = cyl(r * 0.45, h, (x, y, z + sign * h * 0.95), verts=6, bv=0)
    else:
        head = cyl(r, h, (x + sign * h / 2, y, z), axis='X', verts=40, bv=0.5); sock = cyl(r * 0.45, h, (x + sign * h * 0.95, y, z), axis='X', verts=6, bv=0)
    return boolean(head, sock)

def prism_xz(pts, depth):
    bm = bmesh.new()
    vs = [bm.verts.new((x, -depth / 2, z)) for (x, z) in pts]
    f = bm.faces.new(vs); ext = bmesh.ops.extrude_face_region(bm, geom=[f])
    for v in [g for g in ext['geom'] if isinstance(g, bmesh.types.BMVert)]: v.co.y += depth
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new('prism'); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new('prism', me); bpy.context.collection.objects.link(ob); return ob

def bail(x, z, r=9.0, t=1.0):
    """a wire bail (D-ring) standing out of a -x face: half a torus in the x-z plane"""
    bpy.ops.mesh.primitive_torus_add(major_radius=r, minor_radius=t, major_segments=40, minor_segments=10, location=(x, 0, z), rotation=(math.pi / 2, 0, 0))
    ob = bpy.context.object; sel(ob); bpy.ops.object.transform_apply(rotation=True)
    return boolean(ob, box(2 * r + 4, 4 * t + 4, 2 * r + 4, (x + r + 2, 0, z), bv=0))   # keep the -x half

parts = {}
def keep(name, groups):
    out = []
    for ob, mat in groups:
        apply_all(ob)
        me = ob.data
        bm = bmesh.new(); bm.from_mesh(me); bmesh.ops.triangulate(bm, faces=bm.faces[:]); bm.to_mesh(me); bm.free(); me.update()
        # smooth only across edges under 32 deg (flat faces with holes keep flat normals); the operator exists from Blender 4.1
        sel(ob)
        try: bpy.ops.object.shade_smooth_by_angle(angle=32 * D2R)
        except Exception:
            try: bpy.ops.object.shade_auto_smooth(angle=32 * D2R); apply_all(ob)
            except Exception: bpy.ops.object.shade_flat()
        me = ob.data
        mw = ob.matrix_world; nm = mw.to_3x3().inverted().transposed()
        pos, nrm, idx, vmap = [], [], [], {}
        for poly in me.polygons:
            for li in poly.loop_indices:
                l = me.loops[li]; v = me.vertices[l.vertex_index]
                p = mw @ v.co; n = (nm @ (me.corner_normals[li].vector if hasattr(me, 'corner_normals') else l.normal)).normalized()
                key = (round(p.x, 3), round(p.y, 3), round(p.z, 3), round(n.x, 2), round(n.y, 2), round(n.z, 2))
                if key not in vmap:
                    vmap[key] = len(pos) // 3; pos += [p.x, p.y, p.z]; nrm += [max(-127, min(127, round(c * 127))) for c in n]
                idx.append(vmap[key])
        nv = len(pos) // 3; i16 = nv < 65536
        out.append({'mat': mat, 'nv': nv, 'ni': len(idx), 'i16': i16,
                    'pos': base64.b64encode(struct.pack('<%df' % len(pos), *[round(c, 3) for c in pos])).decode(),
                    'nrm': base64.b64encode(struct.pack('<%db' % len(nrm), *nrm)).decode(),
                    'idx': base64.b64encode(struct.pack('<%d%s' % (len(idx), 'H' if i16 else 'I'), *idx)).decode()})
        bpy.data.objects.remove(ob, do_unlink=True)
    parts[name] = out

# ---------------- rail: box-section bar 200 x 44 x 30, channel 14 wide x 11 deep along the top ----------------
rail = box(200, 44, 30, (0, 0, -15), bv=1.2)
boolean(rail, box(210, 14, 22, (0, 0, 0), bv=0))
bevel(rail, 0.6, segs=2, angle=60)
keep('rail', [(rail, STEEL)])

# ---------------- support (H = 50): foot with a tongue, upright with a window, anvil edge, knurled thumb screw, wire bail ----------------
foot = box(34, 54, 10, (-11, 0, -50 + 5), bv=1.0)
tongue = box(28, 13.4, 6, (-11, 0, -50 - 3), bv=0.4)
upright = box(16, 40, 37, (-5, 0, -40 + 18.5 - 0.5), bv=0.9)
boolean(upright, box(5, 50, 22, (-6, 0, -22), bv=0))             # the through window seen on the front cheek
boolean(upright, box(30, 6, 30, (-5, 0, -18), bv=0))             # a centre slot from the top (between the two cheeks)
anvil = cyl(3, 40, (0, 0, -3), axis='Y', verts=48, bv=0.5)
cap = box(6, 40, 3, (-3, 0, -4.5), bv=0.4)
sup = join([foot, tongue, upright, anvil, cap])
thumb = join([knurl(5.5, 6, (-23, 13, -40 + 3)), cyl(3, 4, (-23, 13, -40 - 1), verts=24, bv=0)])
ring = bail(-13.2, -24, r=8.5, t=0.9)
keep('support', [(sup, STEEL), (thumb, POLISH), (ring, POLISH)])

# ---------------- nose: block (44 x 40 x 26) with a side cap screw, V wedge (60 deg) to an R3 loading edge at z = 0 ----------------
arc = [(3 * math.cos(a), 3 + 3 * math.sin(a)) for a in [(-30 - i * 120 / 16) * D2R for i in range(17)]]
wedge = prism_xz([(14, 30), (14, 16.0)] + arc + [(-14, 16.0), (-14, 30)], 40)
bevel(wedge, 0.6, segs=2, angle=50)
block = box(44, 40, 26, (0, 0, 30 + 13), bv=1.4)
boolean(block, cyl(2.5, 50, (8, 0, 47), axis='Y', verts=24, bv=0))   # a cross hole through the block
screw = cap_screw(22, 6, 46, r=3.6, h=4, axis='X', sign=1)
keep('nose', [(join([wedge, block]), STEEL), (screw, BLACK)])

# ---------------- head: knurled nut, collar, shank with a flat and a cross hole, chamfered top ----------------
nut = knurl(14, 11, (0, 0, 5.5), ridges=72, depth=0.8)
collar = cyl(10, 4, (0, 0, 13), verts=48, bv=0.5)
shank = cyl(8, 44, (0, 0, 15 + 22), verts=64, bv=1.0, segs=3)
boolean(shank, box(10, 30, 26, (8 + 5 - 1.6, 0, 40), bv=0))       # the flat on one side
boolean(shank, cyl(2.6, 30, (0, 0, 46), axis='Y', verts=24, bv=0))  # cross hole
setscrew = cap_screw(-13.5, 0, 6, r=2.6, h=2.5, axis='X', sign=-1)
keep('head', [(join([nut, collar, shank]), POLISH), (setscrew, BLACK)])

# ---------------- bar: a stainless spreader for 4-point loading ----------------
bar = box(100, 42, 14, (0, 0, 7), bv=1.4)
keep('bar', [(bar, STEEL), (join([cap_screw(-40, 0, 14, r=3.6, h=3.6), cap_screw(40, 0, 14, r=3.6, h=3.6)]), BLACK)])

# ---------------- pedestal: disc, knurled ring, shank with a cross hole and a set screw ----------------
disc = cyl(20, 6, (0, 0, -3), verts=64, bv=0.8)
ringk = knurl(27, 14, (0, 0, -6 - 7), ridges=96, depth=0.9)
neck = cyl(15, 6, (0, 0, -20 - 3), verts=64, bv=0.5)
shank2 = cyl(13, 50, (0, 0, -26 - 25), verts=64, bv=1.0, segs=3)
boolean(shank2, cyl(3, 40, (0, 0, -60), axis='X', verts=24, bv=0))
set2 = cap_screw(0, -27, -13, r=2.8, h=3, axis='Z')       # placeholder rotated below
bpy.data.objects.remove(set2, do_unlink=True)
set2 = cyl(3, 6, (0, -13 - 2, -40), axis='Y', verts=24, bv=0.4)
keep('pedestal', [(join([disc, neck, shank2]), POLISH), (ringk, POLISH), (set2, BLACK)])

with open(os.path.join(OUT, 'rig.json'), 'w') as f: json.dump({'parts': parts, 'units': 'mm', 'supportH': 50}, f, separators=(',', ':'))
print('RIG_DONE', {k: sum(g['ni'] // 3 for g in v) for k, v in parts.items()}, os.path.getsize(os.path.join(OUT, 'rig.json')) // 1024, 'KB')
