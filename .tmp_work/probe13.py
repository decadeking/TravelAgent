# -*- coding: utf-8 -*-
import zipfile
from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
def q(t): return "{%s}%s" % (W, t)

SRC = r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\src_draft.docx"
z = zipfile.ZipFile(SRC)
root = etree.fromstring(z.read("word/document.xml"))
z.close()
body = root.find(q("body"))
paras = [c for c in body if c.tag == q("p")]

def dump(el, ind=0):
    tag = etree.QName(el).localname
    attrs = " ".join('%s=%s' % (etree.QName(k).localname, v) for k, v in el.attrib.items())
    txt = ""
    if tag == "t":
        txt = " " + repr(el.text)
    line = "  " * ind + tag + (" [" + attrs + "]" if attrs else "") + txt
    lines = [line]
    for c in el:
        lines.extend(dump(c, ind + 1))
    return lines

targets = [102, 103, 104, 121, 134, 135, 140, 169, 170, 196, 197, 299, 33, 34, 35, 36, 38, 208, 221, 224, 234, 244, 261, 262, 268, 277, 297, 331, 333, 257, 155, 127, 73, 32]
out = []
for i in targets:
    out.append("=== P%d ===" % i)
    p = paras[i]
    out.extend(dump(p))
    out.append("")
open(r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\p13.txt", "w", encoding="utf-8").write("\n".join(out))
print("done")
