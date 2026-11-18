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
page.write_text(body, encoding='utf-8')
head = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
        '<style>body{margin:0;font:14px system-ui}img{max-width:100%}[hidden]{display:none!important}</style></head><body>')
full = head.replace('<style>', '<title>Graded TPMS Lattice Designer</title><style>') + body + '</body></html>'
(here / 'gyroid_designer_local.html').write_text(full, encoding='utf-8')
# 4. index.html: the same full document, served by the website (Cloudflare Pages, deployed from the GitHub repo)
(here / 'index.html').write_text(full, encoding='utf-8')
print('fe_core.js synced; wrote', here / 'gyroid_designer_local.html', 'and index.html')
