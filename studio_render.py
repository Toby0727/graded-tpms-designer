# Renders the two studio images the page uses (run with Blender 4.x / 5.x, Cycles):
#   assets/studio_backdrop.jpg  1920x1080  a seamless light-grey infinity cove, the 3D view's background
#   assets/studio_env.jpg       1024x512   an equirectangular studio (grey room, three softboxes) for the part's reflections
# Usage:  blender -b -P studio_render.py
import bpy, math, os, sys
from mathutils import Vector

EXPO = 0.0
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets')
os.makedirs(OUT, exist_ok=True)

def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.samples = 96
    sc.cycles.use_denoising = True
    try: sc.cycles.device = 'GPU'
    except Exception: pass
    sc.view_settings.view_transform = 'AgX'
    try: sc.view_settings.look = 'AgX - Base Contrast'
    except Exception: pass
    sc.world = bpy.data.worlds.new('W')
    sc.world.use_nodes = True
    sc.world.node_tree.nodes['Background'].inputs[0].default_value = (0.6, 0.6, 0.6, 1)
    sc.world.node_tree.nodes['Background'].inputs[1].default_value = 0.15
    sc.view_settings.exposure = EXPO
    return sc

def mat(name, rgb, rough=0.65):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']; b.inputs['Base Color'].default_value = (*rgb, 1); b.inputs['Roughness'].default_value = rough
    return m

def emit(name, strength, rgb=(1, 1, 1)):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    o = nt.nodes.new('ShaderNodeOutputMaterial'); e = nt.nodes.new('ShaderNodeEmission')
    e.inputs[0].default_value = (*rgb, 1); e.inputs[1].default_value = strength
    nt.links.new(e.outputs[0], o.inputs[0]); return m

def plane(name, size, loc, rot, m):
    bpy.ops.mesh.primitive_plane_add(size=1, location=loc, rotation=rot)
    ob = bpy.context.object; ob.name = name; ob.scale = (size[0], size[1], 1); ob.data.materials.append(m); return ob

def look_at(ob, target):
    d = Vector(target) - ob.location; ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()

def cove(m, r=4.0, x=40.0):
    # profile in (y, z): floor from y=-30 to 0, quarter circle of radius r up to the wall, wall up to z=30
    prof = [(-30.0, 0.0)] + [(r * math.sin(a), r - r * math.cos(a)) for a in [i * (math.pi / 2) / 24 for i in range(25)]] + [(r, 30.0)]
    verts, faces = [], []
    for (y, z) in prof: verts += [(-x, y, z), (x, y, z)]
    for i in range(len(prof) - 1): faces.append((2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2))
    me = bpy.data.meshes.new('cove'); me.from_pydata(verts, [], faces); me.update()
    for p in me.polygons: p.use_smooth = True
    ob = bpy.data.objects.new('cove', me); bpy.context.collection.objects.link(ob); me.materials.append(m); return ob

# ---------- 1. backdrop ----------
EXPO = 1.35   # a near-white cove (the user asked for a whiter, brighter look)
sc = reset()
grey = mat('cove', (0.80, 0.80, 0.79), 0.8)
cove(grey)
key = plane('key', (9, 5), (-5, -6, 9), (0, 0, 0), emit('k', 9.0, (1.0, 0.985, 0.96)))
look_at(key, (0, 2, 1))
fill = plane('fill', (7, 4), (7, -7, 5), (0, 0, 0), emit('f', 6.5, (0.96, 0.98, 1.0)))
look_at(fill, (0, 2, 1))
top = plane('top', (14, 3), (0, -1, 12), (0, 0, 0), emit('t', 4.0))
look_at(top, (0, 0, 0))
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
cam.location = (0, -16, 2.4); look_at(cam, (0, 2, 2.0)); cam.data.lens = 45
sc.render.resolution_x, sc.render.resolution_y = 1920, 1080
sc.render.image_settings.file_format = 'JPEG'; sc.render.image_settings.quality = 88
sc.render.filepath = os.path.join(OUT, 'studio_backdrop.jpg')
bpy.ops.render.render(write_still=True)

# ---------- 2. equirectangular studio for reflections ----------
# a dark room so the softboxes stand out in the chrome (a light room reflects as flat grey)
EXPO = 0.0
sc = reset()
room = mat('room', (0.16, 0.16, 0.16), 0.9)
bpy.ops.mesh.primitive_cube_add(size=12, location=(0, 0, 3)); box = bpy.context.object
box.data.materials.append(room)
bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.flip_normals(); bpy.ops.object.mode_set(mode='OBJECT')
floor = plane('floor', (12, 12), (0, 0, -1.2), (0, 0, 0), mat('fl', (0.30, 0.30, 0.29), 0.6))
k1 = plane('soft_key', (3.2, 1.6), (-2.6, -2.2, 3.4), (0, 0, 0), emit('k1', 14.0, (1.0, 0.98, 0.95))); look_at(k1, (0, 0, 0))
k2 = plane('soft_fill', (2.4, 1.4), (3.0, -1.0, 2.0), (0, 0, 0), emit('k2', 6.0, (0.95, 0.98, 1.0))); look_at(k2, (0, 0, 0))
k3 = plane('strip_top', (6.0, 0.5), (0.4, 1.2, 4.6), (0, 0, 0), emit('k3', 10.0)); look_at(k3, (0, 0, 0))
k4 = plane('strip_back', (0.5, 3.0), (0.0, 4.5, 1.6), (0, 0, 0), emit('k4', 5.0)); look_at(k4, (0, 0, 0))
cam = bpy.data.objects.new('pano', bpy.data.cameras.new('pano')); sc.collection.objects.link(cam); sc.camera = cam
cam.data.type = 'PANO'
try: cam.data.panorama_type = 'EQUIRECTANGULAR'
except Exception: cam.data.cycles.panorama_type = 'EQUIRECTANGULAR'
cam.location = (0, 0, 0.2); cam.rotation_euler = (math.pi / 2, 0, -math.pi / 2)   # looks along +x, z up
sc.render.resolution_x, sc.render.resolution_y = 1024, 512
sc.render.image_settings.file_format = 'JPEG'; sc.render.image_settings.quality = 90
sc.render.filepath = os.path.join(OUT, 'studio_env.jpg')
bpy.ops.render.render(write_still=True)
print('STUDIO_DONE', OUT)
