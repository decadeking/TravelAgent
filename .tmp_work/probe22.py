import zipfile, re
from lxml import etree as ET

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
V = 'urn:schemas-microsoft-com:vml'
q = lambda t: '{%s}%s' % (W, t)

src = '.tmp_work/src_draft.docx'
out = []
with zipfile.ZipFile(src) as z:
    root = ET.fromstring(z.read('word/document.xml'))
    rels = ET.fromstring(z.read('word/_rels/document.xml.rels'))
    media = [n for n in z.namelist() if n.startswith('word/media/')]
body = root.find(q('body'))
paras = [c for c in body if c.tag == q('p')]

out.append('--- RELS ---')
for rel in rels:
    out.append('%s -> %s (%s)' % (rel.get('Id'), rel.get('Target'), rel.get('Type').split('/')[-1]))
out.append('--- MEDIA ---')
for m in media:
    out.append(m)

out.append('--- PICTS ---')
for i, p in enumerate(paras):
    pics = p.findall('.//{%s}pict' % W)
    if not pics:
        continue
    rid = []
    for pc in pics:
        for im in pc.iter('{%s}imagedata' % V):
            rid.append(im.get('{%s}id' % R))
    runs = p.findall(q('r'))
    info = []
    for j, r in enumerate(runs):
        t = ''.join(x.text or '' for x in r.findall(q('t')))
        info.append('%d:[%s|%s]' % (j, 'pict' if r.find(q('pict')) is not None else 'txt', t[:20]))
    out.append('P%d rids=%s runs=%s' % (i, rid, ' '.join(info)))

open('.tmp_work/probe22.txt', 'w', encoding='utf-8').write('\n'.join(out))
print('OK', len(out))
