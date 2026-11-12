# -*- coding: utf-8 -*-
import zipfile
from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
def q(t): return "{%s}%s" % (W, t)

src = r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\src_draft.docx"
z = zipfile.ZipFile(src)
root = etree.fromstring(z.read("word/document.xml"))
body = root.find(q("body"))
tbls = [c for c in body if c.tag == q("tbl")]

out = []
def w(s=""): out.append(str(s))

t = tbls[2]
w("TBL2 xml:")
s = etree.tostring(t, encoding="unicode")
w(s[:6000])
w()

for name in ["word/header1.xml", "word/header2.xml", "word/header3.xml"]:
    w("=== " + name)
    r = etree.fromstring(z.read(name))
    for pi, p in enumerate(r.iter(q("p"))):
        w(" p%d jc=%s" % (pi, (p.find(q("pPr")).find(q("jc")).get(q("val")) if p.find(q("pPr")) is not None and p.find(q("pPr")).find(q("jc")) is not None else None)))
        for ri, run in enumerate(p.findall(q("r"))):
            col = run.find(q("rPr")).find(q("color")) if run.find(q("rPr")) is not None else None
            w("   r%d color=%s text=%r" % (ri, col.get(q("val")) if col is not None else None,
                                           "".join(x.text or "" for x in run.findall(q("t")))))
    w()

open(r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\probe28.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok", len(out))
