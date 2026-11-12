import zipfile
from lxml import etree as ET

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
q = lambda t: '{%s}%s' % (W, t)
src = '.tmp_work/src_draft.docx'
with zipfile.ZipFile(src) as z:
    root = ET.fromstring(z.read('word/document.xml'))
body = root.find(q('body'))
paras = [c for c in body if c.tag == q('p')]
xml = ET.tostring(paras[111], pretty_print=True, encoding='unicode')
i = xml.find('<w:pict')
open('.tmp_work/probe24.txt', 'w', encoding='utf-8').write(xml[i:i+4000])
print('OK')
