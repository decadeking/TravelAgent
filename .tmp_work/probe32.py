# -*- coding: utf-8 -*-
import zipfile
from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
def q(t):
    return "{%s}%s" % (W, t)

src = r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\src_draft.docx"
z = zipfile.ZipFile(src)
root = etree.fromstring(z.read("word/document.xml"))
body = root.find(q("body"))
paras = [c for c in body if c.tag == q("p")]

out = []
for i in [102, 127, 155, 178, 257, 277, 297, 324]:
    p = paras[i]
    out.append("=== P%d" % i)
    for k, r in enumerate([c for c in p if c.tag == q("r")]):
        seg = []
        for c in r:
            ln = etree.QName(c).localname
            if ln == "t":
                seg.append(repr(c.text or ""))
            elif ln == "br":
                seg.append("BR")
            elif ln == "tab":
                seg.append("TAB")
        rp = r.find(q("rPr"))
        col = rp.find(q("color")) if rp is not None else None
        seg.append("RED" if (col is not None and col.get(q("val")) == "FF0000") else "-")
        out.append("  r%d %s" % (k, " ".join(seg)))
    out.append("")

open(r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\probe32.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok")