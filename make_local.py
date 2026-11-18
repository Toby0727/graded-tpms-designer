# 1. copies fe_core.js into gyroid_designer.html between /*FE_CORE_BEGIN*/ and /*FE_CORE_END*/ (the artifact is one file;
#    fe_core.js stays the source that node fe_validate.js tests);
# 2. copies preload_fe.json (FE results solved in advance, see the 11-10 journal) between /*PRELOAD_BEGIN*/ and /*PRELOAD_END*/;
# 3. wraps the artifact source (no <html>/<head>) in a full document so it also runs as a plain local file
#    (double-click -> browser). Output: gyroid_designer_local.html
import pathlib, json
here = pathlib.Path(__file__).parent
page = here / 'gyroid_designer.html'
body = page.read_text(encoding='utf-8')

def put(body, a, b, text):
    i, j = body.index(a) + len(a), body.index(b)
    return body[:i] + text + body[j:]

core = (here / 'fe_core.js').read_text(encoding='utf-8')
assert '</script' not in core.lower()
body = put(body, '/*FE_CORE_BEGIN*/', '/*FE_CORE_END*/', '\n' + core + '\n')
pre = here / 'preload_fe.json'
if pre.exists():
    data = json.loads(pre.read_text(encoding='utf-8'))
    body = put(body, '/*PRELOAD_BEGIN*/', '/*PRELOAD_END*/', json.dumps(data, separators=(',', ':'), ensure_ascii=False))
    print('preload:', len(data['list']), 'results')
# 3. the Blender studio images (studio_render.py) as data URIs: the 3D view's backdrop and the reflection map
import base64
for tag, name in (('BACKDROP', 'studio_backdrop.jpg'), ('ENVMAP', 'studio_env.jpg')):
    f = here / 'assets' / name
    if f.exists() and f'/*{tag}_BEGIN*/' in body:
        uri = 'data:image/jpeg;base64,' + base64.b64encode(f.read_bytes()).decode()
        body = put(body, f'/*{tag}_BEGIN*/', f'/*{tag}_END*/', json.dumps(uri))
        print(tag.lower(), f.stat().st_size // 1024, 'KB')
# 4. the Blender fixture meshes (rig_model.py) as a JSON object
rig = here / 'assets' / 'rig.json'
if rig.exists() and '/*RIG_BEGIN*/' in body:
    body = put(body, '/*RIG_BEGIN*/', '/*RIG_END*/', rig.read_text(encoding='utf-8'))
    print('rig', rig.stat().st_size // 1024, 'KB')
page.write_text(body, encoding='utf-8')
head = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
        '<style>body{margin:0;font:14px system-ui}img{max-width:100%}[hidden]{display:none!important}</style></head><body>')
icon = ("<link rel=\"icon\" href=\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
        "%3Crect width='32' height='32' rx='6' fill='%2305060a'/%3E%3Cpath d='M4 16c4-8 8-8 12 0s8 8 12 0' fill='none' "
        "stroke='%239fb6c8' stroke-width='3'/%3E%3C/svg%3E\">")
full = head.replace('<style>', '<title>Graded TPMS Lattice Designer</title>' + icon + '<style>') + body + '</body></html>'
(here / 'gyroid_designer_local.html').write_text(full, encoding='utf-8')
# 4. index.html: the same full document, served by the website (Cloudflare Pages, deployed from the GitHub repo)
(here / 'index.html').write_text(full, encoding='utf-8')
print('fe_core.js synced; wrote', here / 'gyroid_designer_local.html', 'and index.html')
