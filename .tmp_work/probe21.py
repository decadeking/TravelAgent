import zipfile, io, sys
from lxml import etree as ET

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
V = 'urn:schemas-microsoft-com:vml'
q = lambda t: '{%s}%s' % (W, t)

src = '.tmp_work/src_draft.docx'
with zipfile.ZipFile(src) as z:
    data = z.read('word/document.xml')
root = ET.fromstring(data)
body = root.find(q('body'))
paras = [c for c in body if c.tag == q('p')]
tbls = [c for c in body if c.tag == q('tbl')]

targets = [181, 211, 246, 294, 295, 296, 297, 324, 342]
out = []
out.append('PARAS %d TABLES %d CHILD %d' % (len(paras), len(tbls), len(body)))

def dump(el, ind=0):
    if not isinstance(el.tag, str):
        out.append('  ' * ind + '<!--comment-->')
        return
    name = ET.QName(el).localname
    attrs = ' '.join('%s=%s' % (ET.QName(k).localname if isinstance(k, str) else k, v) for k, v in el.attrib.items())
    ns = ET.QName(el).namespace
    pre = ''
    if ns == V: pre = 'v:'
    if ns == 'urn:schemas-microsoft-com:office:office': pre = 'o:'
    if ns == 'http://schemas.microsoft.com/office/word/2010/wordml': pre = 'w10:'
    out.append('  ' * ind + '<%s%s%s>' % (pre, name, (' ' + attrs) if attrs else ''))
    if el.text and el.text.strip():
        out.append('  ' * (ind + 1) + 'TEXT: ' + el.text.strip()[:120])
    for c in el:
        dump(c, ind + 1)

for i in targets:
    if i < len(paras):
        out.append('===== P%d =====' % i)
        dump(paras[i])
out.append('===== BODY TAIL =====')
for c in list(body)[-3:]:
    dump(c)

open('.tmp_work/probe21.txt', 'w', encoding='utf-8').write('\n'.join(out))
print('OK', len(out))
