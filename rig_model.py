# Models the bending fixture shown in the page's 3D view (a universal-testing-machine 3-point jig: slotted rail with a scale,
# two upright plate supports, a stepped black loading nose under a load cell, a pedestal under the rail) and exports each
# part as a small mesh file the page draws with WebGL.  Run:  blender -b -P rig_model.py
# Output: assets/rig.json  {parts: {name: {mat, pos (b64 float32 mm), nrm (b64 int8), idx (b64 uint32)}}}
# Part frames (mm, x = span, y = width, z = up):
#   rail      top face at z = 0, centred, 200 long (the page stretches it in x to fit the span)
#   support   the contact edge at z = 0 (the beam's underside), standing on the rail at z = -45
#   nose      the rounded tip at z = 0 (the beam's top face), the block rises to z = +55
#   head      the coupling, nut and load cell, starting at z = 0 (the top of the nose)
#   bar       a spreader plate for 4-point loading, bottom at z = 0, 100 long (stretched in x)
#   pedestal  under the rail, top at z = 0
import bpy, bmesh, math, os, json, base64, struct
from mathutils import Vector, Matrix

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets')
os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
STEEL, BLACK, POLISH = 0, 1, 2

def apply_all(ob):
    bpy.context.view_layer.objects.active = ob
    for o in bpy.context.selected_objects: o.select_set(False)
    ob.select_set(True)
    for m in list(ob.modifiers): bpy.ops.object.modifier_apply(modifier=m.name)

def box(sx, sy, sz, loc, bevel=0.8, segs=3):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc); ob = bpy.context.object; ob.scale = (sx, sy, sz)
    bpy.ops.object.transform_apply(scale=True)
    if bevel > 0:
        b = ob.modifiers.new('bv', 'BEVEL'); b.width = bevel; b.segments = segs; b.limit_method = 'ANGLE'
    return ob

def cyl(r, h, loc, axis='Z', verts=48, bevel=0.6, segs=2):
    rot = {'Z': (0, 0, 0), 'X': (0, math.pi / 2, 0), 'Y': (math.pi / 2, 0, 0)}[axis]
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=h, location=loc, rotation=rot); ob = bpy.context.object
    if bevel > 0:
        b = ob.modifiers.new('bv', 'BEVEL'); b.width = bevel; b.segments = segs; b.limit_method = 'ANGLE'
    return ob

def cut(target, tool):
    m = target.modifiers.new('cut', 'BOOLEAN'); m.operation = 'DIFFERENCE'; m.object = tool; m.solver = 'EXACT'
    apply_all(target); bpy.data.objects.remove(tool, do_unlink=True)

def join(obs):
    for o in obs: apply_all(o)
    for o in bpy.context.selected_objects: o.select_set(False)
    for o in obs: o.select_set(True)
    bpy.context.view_layer.objects.active = obs[0]; bpy.ops.object.join(); return obs[0]

parts = {}
def keep(name, groups):
    """groups: list of (object, material id); each group exported as its own sub-mesh so materials stay apart."""
    out = []
    for ob, mat in groups:
        apply_all(ob)
        me = ob.data
        bm = bmesh.new(); bm.from_mesh(me); bmesh.ops.triangulate(bm, faces=bm.faces[:]); bm.to_mesh(me); bm.free()
        me.update()
        try: me.shade_smooth_by_angle(angle=math.radians(35))
        except Exception:
            for p in me.polygons: p.use_smooth = True
        mw = ob.matrix_world; nm = mw.to_3x3().inverted().transposed()
        pos, nrm, idx, vmap = [], [], [], {}
        for poly in me.polygons:
            for li in poly.loop_indices:
                l = me.loops[li]; v = me.vertices[l.vertex_index]
                p = mw @ v.co; n = (nm @ (l.normal if poly.use_smooth else poly.normal)).normalized()
                key = (round(p.x, 3), round(p.y, 3), round(p.z, 3), round(n.x, 2), round(n.y, 2), round(n.z, 2))
                if key not in vmap:
                    vmap[key] = len(pos) // 3; pos += [p.x, p.y, p.z]; nrm += [max(-127, min(127, round(c * 127))) for c in n]
                idx.append(vmap[key])
        out.append({'mat': mat, 'pos': base64.b64encode(struct.pack('<%df' % len(pos), *pos)).decode(),
                    'nrm': base64.b64encode(struct.pack('<%db' % len(nrm), *nrm)).decode(),
                    'idx': base64.b64encode(struct.pack('<%dI' % len(idx), *idx)).decode(), 'nv': len(pos) // 3, 'ni': len(idx)})
        bpy.data.objects.remove(ob, do_unlink=True)
    parts[name] = out

# ---------- rail: 200 x 60 x 12, a through slot 150 x 8 along x, top face at z = 0 ----------
rail = box(200, 60, 12, (0, 0, -6), bevel=1.0)
apply_all(rail)
slot = box(150, 8, 20, (0, 0, -6), bevel=0); slot2 = cyl(4, 20, (75, 0, -6), verts=32, bevel=0); slot3 = cyl(4, 20, (-75, 0, -6), verts=32, bevel=0)
tool = join([slot, slot2, slot3]); cut(rail, tool)
keep('rail', [(rail, STEEL)])

# ---------- support: a 6 mm plate, 44 wide, top edge rounded (radius 3) at z = 0, on a foot block at z = -45 ----------
plate = box(6, 44, 39, (0, 0, -3 - 19.5), bevel=0.6)
edge = cyl(3, 44, (0, 0, -3), axis='Y', verts=40, bevel=0.6)
foot = box(22, 50, 10, (-5, 0, -45 + 5), bevel=1.2)
bolt = cyl(4.2, 4, (-11, 14, -45 + 12), verts=6, bevel=0.4); bolt2 = cyl(4.2, 4, (-11, -14, -45 + 12), verts=6, bevel=0.4)
sup = join([plate, edge, foot])
keep('support', [(sup, STEEL), (join([bolt, bolt2]), POLISH)])

# ---------- nose: stepped black block, rounded tip at z = 0 ----------
tip = cyl(4, 46, (0, 0, 4), axis='Y', verts=40, bevel=0.5)
low = box(8, 46, 22, (0, 0, 4 + 11), bevel=0.4)
mid = box(26, 46, 26, (0, 0, 26 + 13), bevel=1.0)
nose = join([tip, low, mid])
keep('nose', [(nose, BLACK)])

# ---------- head: hex nut, rod, collar, load cell with a side knob, from z = 0 up ----------
nut = cyl(11, 9, (0, 0, 4.5), verts=6, bevel=0.6)
rod = cyl(6, 14, (0, 0, 9 + 7), verts=32)
collar = cyl(27, 7, (0, 0, 23 + 3.5), verts=64, bevel=0.8)
cell = cyl(23, 58, (0, 0, 30 + 29), verts=64, bevel=1.4)
knob = cyl(8, 16, (0, -30, 52), axis='Y', verts=40, bevel=1.0)
topcap = cyl(14, 10, (0, 0, 88 + 5), verts=48, bevel=0.8)
keep('head', [(join([nut, rod, cell, topcap]), POLISH), (collar, BLACK), (knob, POLISH)])

# ---------- bar: spreader for 4-point, 100 x 46 x 14, bottom at z = 0 ----------
keep('bar', [(box(100, 46, 14, (0, 0, 7), bevel=1.0), BLACK)])

# ---------- pedestal: black disc, steel post with a knob, flange with bolts, top at z = 0 ----------
disc = cyl(28, 8, (0, 0, -4), verts=64, bevel=0.8)
post = cyl(16, 46, (0, 0, -8 - 23), verts=48, bevel=0.8)
knob2 = cyl(7, 14, (0, -21, -30), axis='Y', verts=32, bevel=0.8)
flange = cyl(36, 12, (0, 0, -54 - 6), verts=64, bevel=1.0)
bolts = [cyl(4, 4, (28 * math.cos(a), 28 * math.sin(a), -54 + 2), verts=6, bevel=0.3) for a in [i * math.pi / 3 + 0.3 for i in range(6)]]
keep('pedestal', [(disc, BLACK), (join([post, flange]), STEEL), (join([knob2] + bolts), POLISH)])

with open(os.path.join(OUT, 'rig.json'), 'w') as f: json.dump({'parts': parts, 'units': 'mm'}, f, separators=(',', ':'))
print('RIG_DONE', {k: sum(g['ni'] // 3 for g in v) for k, v in parts.items()})
