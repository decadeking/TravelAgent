# -*- coding: utf-8 -*-
import zipfile
from lxml import etree

SRC = r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\src_draft.docx"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
def q(t): return "{%s}%s" % (W, t)

z = zipfile.ZipFile(SRC)
root = etree.fromstring(z.read("word/document.xml"))
body = root.find(q("body"))
paras = [c for c in body if c.tag == q("p")]

out = []
out.append("paras=%d" % len(paras))
for i, p in enumerate(paras):
    ppr = p.find(q("pPr"))
    has_sect = ppr is not None and ppr.find(q("sectPr")) is not None
    brs = p.findall(".//" + q("br"))
    pbr = [b for b in brs if b.get(q("type")) == "page"]
    if has_sect or pbr:
        t = "".join(x.text or "" for x in p.iter(q("t")))
        out.append("P%-4d sect=%s pagebr=%d %r" % (i, has_sect, len(pbr), t[:40]))
        if has_sect:
            sp = ppr.find(q("sectPr"))
            tp = sp.find(q("type"))
            out.append("      type=%s  has_pgNum=%s %s" % (
                tp.get(q("val")) if tp is not None else None,
                sp.find(q("pgNumType")) is not None,
                etree.tostring(sp.find(q("pgNumType")), encoding="unicode") if sp.find(q("pgNumType")) is not None else ""))
out.append("sections in body: %d" % len(body.findall(".//" + q("sectPr"))))
open(r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\p15.txt", "w", encoding="utf-8").write("\n".join(out))
print("\n".join(out))
