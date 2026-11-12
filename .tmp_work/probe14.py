# -*- coding: utf-8 -*-
import zipfile, re
from lxml import etree

SRC = r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\src_draft.docx"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
def q(t): return "{%s}%s" % (W, t)

z = zipfile.ZipFile(SRC)
xml = z.read("word/document.xml")
root = etree.fromstring(xml)
body = root.find(q("body"))
paras = [c for c in body if c.tag == q("p")]

def dump(el, ind=0):
    tag = etree.QName(el).localname
    attrs = " ".join('%s=%s' % (etree.QName(k).localname, v) for k, v in el.attrib.items())
    txt = " " + repr(el.text) if tag in ("t", "instrText") and el.text else ""
    lines = ["  " * ind + tag + (" [" + attrs + "]" if attrs else "") + txt]
    for c in el:
        lines.extend(dump(c, ind + 1))
    return lines

out = []
for i in (75, 76, 79, 80, 81, 137, 144, 146, 264, 265, 271, 272):
    out.append("=" * 20 + " P%d " % i + "=" * 20)
    out.extend(dump(paras[i]))
    out.append("")
open(r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\p14.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok", len(out))
