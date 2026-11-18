# Models the bending fixture shown in the page's 3D view, after a universal-testing-machine 3-point jig (photo reference):
# a slotted stainless rail with a scale, two L-shaped plate supports on slider blocks with cap screws, a stepped black
# loading nose, a stud with nut and washer, a black collar and a polished load cell with a side knob and top boss, and a
# pedestal under the rail (black clamp disc, post with knob, flange with six cap screws, boss).
# Run:  blender -b -P rig_model.py      Output: assets/rig.json
# Part frames (mm, x = span, y = width, z = up):
#   rail      top face at z = 0, centred, 200 long (the page stretches it in x to fit the span)
#   support   the contact edge at z = 0 (the beam's underside), the slider block on the rail at z = -45; the block sits on
#             the -x side (the page mirrors it for the support on the +x side)
#   nose      the loading edge at z = 0 (the beam's top face), the block rises to z = +58
#   head      stud, nut, collar and load cell, from z = 0 (the top of the nose)
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

def cyl(r, h, loc, axis='Z', verts=64, bv=0.6, segs=2, rot=None):
    r0 = {'Z': (0, 0, 0), 'X': (0, math.pi / 2, 0), 'Y': (math.pi / 2, 0, 0)}[axis] if rot is None else rot
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=h, location=loc, rotation=r0); ob = bpy.context.object
    sel(ob); bpy.ops.object.transform_apply(rotation=True)
    return bevel(ob, bv, segs) if bv > 0 else ob

def boolean(target, tool, op='DIFFERENCE'):
    m = target.modifiers.new('b', 'BOOLEAN'); m.operation = op; m.object = tool; m.solver = 'EXACT'
    apply_all(target); bpy.data.objects.remove(tool, do_unlink=True); return target

def join(obs):
    obs = [o for o in obs if o is not None]
    for o in obs: apply_all(o)
    for o in bpy.context.selected_objects: o.select_set(False)
    for o in obs: o.select_set(True)
    bpy.context.view_layer.objects.active = obs[0]; bpy.ops.object.join(); return obs[0]

def cap_screw(x, y, z, r=4.2, h=4.6, up=1):
    """socket-head cap screw standing on z (head up), with a hex socket and a chamfered rim"""
    head = cyl(r, h, (x, y, z + up * h / 2), verts=40, bv=0.5, segs=2)
    sock = cyl(r * 0.46, h, (x, y, z + up * h * 0.95), verts=6, bv=0)
    return boolean(head, sock)

def hex_nut(r, h, loc):
    n = cyl(r, h, loc, verts=6, bv=0)
    ch = cyl(r * 0.98, h, loc, verts=64, bv=0)       # chamfer: intersect the hex with a bevelled round body
    bevel(ch, h * 0.22, segs=1, angle=30)
    return boolean(n, ch, 'INTERSECT')

def thread(r, h, z0, pitch=1.4):
    rings = []
    n = int(h / pitch)
    for i in range(n): rings.append(cyl(r if i % 2 == 0 else r * 0.9, pitch, (0, 0, z0 + (i + 0.5) * pitch), verts=40, bv=0))
    return join(rings)

parts = {}
def keep(name, groups):
    out = []
    for ob, mat in groups:
        apply_all(ob)
        me = ob.data
        bm = bmesh.new(); bm.from_mesh(me); bmesh.ops.triangulate(bm, faces=bm.faces[:]); bm.to_mesh(me); bm.free(); me.update()
        try: me.shade_smooth_by_angle(angle=32 * D2R)
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
        nv = len(pos) // 3; i16 = nv < 65536
        out.append({'mat': mat, 'nv': nv, 'ni': len(idx), 'i16': i16,
                    'pos': base64.b64encode(struct.pack('<%df' % len(pos), *[round(c, 3) for c in pos])).decode(),
                    'nrm': base64.b64encode(struct.pack('<%db' % len(nrm), *nrm)).decode(),
                    'idx': base64.b64encode(struct.pack('<%d%s' % (len(idx), 'H' if i16 else 'I'), *idx)).decode()})
        bpy.data.objects.remove(ob, do_unlink=True)
    parts[name] = out

# ---------------- rail: 200 x 56 x 10, rounded corners, a through slot with round ends, two end holes ----------------
rail = box(200, 56, 10, (0, 0, -5), bv=0)
for sx in (-1, 1):                                       # rounded plan corners
    for sy in (-1, 1):
        corner = box(6, 6, 12, (sx * 97, sy * 25, -5), bv=0); ring = cyl(3, 12, (sx * 97 - sx * 3 + sx * 3, sy * 25, -5), verts=24, bv=0)
        corner.location = (sx * 98.5, sy * 26.5, -5); boolean(corner, cyl(4, 14, (sx * 96, sy * 24, -5), verts=32, bv=0))
        boolean(rail, corner)
        bpy.data.objects.remove(ring, do_unlink=True)
bevel(rail, 0.9, segs=2, angle=50)
slot = join([box(150, 8.5, 20, (0, 2, -5), bv=0), cyl(4.25, 20, (75, 2, -5), verts=32, bv=0), cyl(4.25, 20, (-75, 2, -5), verts=32, bv=0)])
boolean(rail, slot)
for sx in (-1, 1): boolean(rail, cyl(3.4, 20, (sx * 88, 2, -5), verts=32, bv=0))
keep('rail', [(rail, STEEL)])

# ---------------- support: L-shaped, plate (6 thick, 46 wide) with a rounded top edge, slider block with a cap screw ----------------
plate = box(6, 46, 33, (0, 0, -3 - 16.5), bv=0.7)
edge = cyl(3, 46, (0, 0, -3), axis='Y', verts=48, bv=0.7)
block = box(26, 52, 11, (-10, 0, -45 + 5.5), bv=1.2)
fillet = box(4, 46, 4, (-4.6, 0, -34 + 0.5), bv=0)           # a small weld fillet between plate and block
boolean(fillet, cyl(4, 50, (-7, 0, -30.5), axis='Y', verts=32, bv=0))
sup = join([plate, edge, block, fillet])
screws = join([cap_screw(-16, 15, -34), cap_screw(-16, -15, -34)])
keep('support', [(sup, STEEL), (screws, BLACK)])

# ---------------- nose: stepped black block, a 45 deg wedge to a rounded loading edge (r 4) at z = 0 ----------------
def prism_xz(pts, depth):
    """a prism from a closed x-z profile, extruded along y over +-depth/2"""
    bm = bmesh.new()
    vs = [bm.verts.new((x, -depth / 2, z)) for (x, z) in pts]
    f = bm.faces.new(vs); ext = bmesh.ops.extrude_face_region(bm, geom=[f])
    for v in [g for g in ext['geom'] if isinstance(g, bmesh.types.BMVert)]: v.co.y += depth
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new('prism'); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new('prism', me); bpy.context.collection.objects.link(ob); return ob
# lower nose: a 60 deg V with a radius-4 loading edge at z = 0, straight sides from z = 18.5 to 34
arc = [(4 * math.cos(a), 4 + 4 * math.sin(a)) for a in [(-30 - i * 120 / 16) * D2R for i in range(17)]]
prof = [(13, 34), (13, 18.5)] + arc + [(-13, 18.5), (-13, 34)]
low = prism_xz(prof, 48)
bevel(low, 0.8, segs=2, angle=50)
upper = box(44, 52, 26, (0, 0, 34 + 13), bv=1.6)
groove = box(46, 54, 1.2, (0, 0, 34 + 4), bv=0)
boolean(upper, groove)
nose = join([low, upper])
keep('nose', [(nose, BLACK)])

# ---------------- head: stud with thread, washer, hex nut, black collar, load cell (grooves, side knob, set-screw hole, top boss) ----------------
z = 0
stud = thread(7, 12, z); z += 12
washer = cyl(13, 2, (0, 0, z + 1), verts=48, bv=0.3); z += 2
nut = hex_nut(12.5, 10, (0, 0, z + 5)); z += 10
neck = cyl(8, 6, (0, 0, z + 3), verts=48, bv=0.4); z += 6
collar = cyl(31, 9, (0, 0, z + 4.5), verts=96, bv=1.6, segs=3); z += 9
cell = cyl(24, 60, (0, 0, z + 30), verts=96, bv=1.6, segs=3)
for gz in (z + 8, z + 52):
    g = cyl(25, 1.4, (0, 0, gz), verts=96, bv=0); boolean(g, cyl(23.4, 3, (0, 0, gz), verts=96, bv=0)); boolean(cell, g)
boolean(cell, cyl(2.6, 12, (24, 0, z + 34), axis='X', verts=24, bv=0))      # set-screw hole on the +x side
kz = z + 34; a = -125 * D2R                                                  # side knob, pointing front-left
knob = cyl(8.5, 16, (0, 0, 0), axis='X', verts=48, bv=1.2, segs=3)
knob_neck = cyl(6, 6, (-10, 0, 0), axis='X', verts=40, bv=0.4)
k = join([knob, knob_neck]); k.location = (0, 0, 0)
for v in k.data.vertices: v.co.x -= 8 + 24 + 5
k.rotation_euler = (0, 0, a + math.pi); k.location = (0, 0, kz); sel(k); bpy.ops.object.transform_apply(location=True, rotation=True)
z += 60
boss = cyl(16, 14, (0, 0, z + 7), verts=64, bv=1.2, segs=3)
boolean(boss, cyl(6, 6, (0, 0, z + 14), verts=40, bv=0))
keep('head', [(join([stud, washer, nut, neck, cell, boss]), POLISH), (collar, BLACK), (k, POLISH)])

# ---------------- bar: spreader for 4-point, black, with two cap screws ----------------
bar = box(100, 50, 15, (0, 0, 7.5), bv=1.4)
keep('bar', [(bar, BLACK), (join([cap_screw(-40, 0, 15), cap_screw(40, 0, 15)]), POLISH)])

# ---------------- pedestal: black clamp disc, neck, post with a knob and a groove, flange with six cap screws, boss ----------------
z = 0
disc = cyl(30, 9, (0, 0, z - 4.5), verts=96, bv=1.4, segs=3); z -= 9
neck2 = cyl(11, 6, (0, 0, z - 3), verts=48, bv=0.4); z -= 6
post = cyl(17, 44, (0, 0, z - 22), verts=96, bv=1.2, segs=3)
g = cyl(18, 1.4, (0, 0, z - 6), verts=96, bv=0); boolean(g, cyl(16.4, 3, (0, 0, z - 6), verts=96, bv=0)); boolean(post, g)
kz2 = z - 26
knob2 = cyl(7, 14, (0, 0, 0), axis='X', verts=40, bv=1.0, segs=3)
for v in knob2.data.vertices: v.co.x -= 7 + 17 + 3
knob2.rotation_euler = (0, 0, -125 * D2R + math.pi); knob2.location = (0, 0, kz2); sel(knob2); bpy.ops.object.transform_apply(location=True, rotation=True)
z -= 44
flange = cyl(38, 12, (0, 0, z - 6), verts=96, bv=1.6, segs=3)
screws2 = join([cap_screw(29 * math.cos(t), 29 * math.sin(t), z, r=3.8, h=4) for t in [i * math.pi / 3 + 0.35 for i in range(6)]])
z -= 12
boss2 = cyl(26, 16, (0, 0, z - 8), verts=96, bv=1.2, segs=3)
keep('pedestal', [(disc, BLACK), (join([neck2, post, flange, boss2]), POLISH), (join([knob2]), POLISH), (screws2, BLACK)])

with open(os.path.join(OUT, 'rig.json'), 'w') as f: json.dump({'parts': parts, 'units': 'mm'}, f, separators=(',', ':'))
print('RIG_DONE', {k: sum(g['ni'] // 3 for g in v) for k, v in parts.items()}, os.path.getsize(os.path.join(OUT, 'rig.json')) // 1024, 'KB')
