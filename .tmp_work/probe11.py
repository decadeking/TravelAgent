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
print("total body children", len(body), "paras", len(paras))
def txt(p):
    return "".join(t.text or "" for t in p.iter(q("t")))
lines = []
for i in (5, 31, 32, 33, 34, 35, 36, 38, 45, 46, 49, 59, 60, 65, 66, 67, 73, 74, 75, 76, 79, 80, 81, 100, 101, 102, 103, 121, 126, 127, 138, 139, 140, 141, 155, 156, 157, 158, 159, 160, 161, 169, 170, 171, 177, 178, 191, 193, 195, 196, 207, 208, 210, 211, 221, 223, 225, 234, 235, 243, 244, 246, 254, 257, 261, 262, 268, 277, 297, 298, 299, 320, 324, 327, 331, 333, 337):
    if i < len(paras):
        lines.append("P%-4d %r" % (i, txt(paras[i])[:50]))
open(r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\p11.txt", "w", encoding="utf-8").write("\n".join(lines))
print("done")
