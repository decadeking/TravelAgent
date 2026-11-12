import zipfile
from lxml import etree as ET

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
q = lambda t: '{%s}%s' % (W, t)
src = '.tmp_work/src_draft.docx'
out = []
with zipfile.ZipFile(src) as z:
    root = ET.fromstring(z.read('word/document.xml'))
body = root.find(q('body'))
paras = [c for c in body if c.tag == q('p')]
for i in (0, 111, 139, 166, 255):
    out.append('===== P%d =====' % i)
    out.append(ET.tostring(paras[i], pretty_print=True, encoding='unicode')[:3000])
open('.tmp_work/probe23.txt', 'w', encoding='utf-8').write('\n'.join(out))
print('OK')
