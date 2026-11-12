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
kids = [c for c in body]
paras = [c for c in kids if c.tag == q("p")]

out = []
out.append("== body child map ==")
for i, c in enumerate(kids):
    tag = etree.QName(c).localname
    if tag == "p":
        pi = paras.index(c)
        txt = "".join(t.text or "" for t in c.iter(q("t")))
        out.append("child%-4d P%-4d %s %r" % (i, pi, tag, txt[:30]))
    else:
        out.append("child%-4d ---- %s" % (i, tag))

targets = [5, 74, 75, 79, 80, 81, 102, 103, 104, 107, 108, 109, 121, 127, 129, 133, 134, 135, 140, 141, 169, 170, 171, 178, 179, 180, 191, 193, 194, 196, 208, 221, 224, 225, 234, 244, 257, 258, 261, 262, 268, 277, 297, 299, 331, 333, 33, 34, 35, 36, 38]
for i in targets:
    p = paras[i]
    out.append("")
    out.append("=== P%d ===" % i)
    ppr = p.find(q("pPr"))
    out.append("pPr: " + (etree.tostring(ppr, encoding="unicode") if ppr is not None else "None"))
    for j, r in enumerate(p.findall(q("r"))):
        rpr = r.find(q("rPr"))
        txt = "".join(t.text or "" for t in r.iter(q("t")))
        kinds = [etree.QName(c).localname for c in r]
        out.append("  r%d %r kinds=%s" % (j, txt, kinds))
        if rpr is not None:
            out.append("     rPr: " + etree.tostring(rpr, encoding="unicode"))

open(r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\p12.txt", "w", encoding="utf-8").write("\n".join(out))
print("done")
