# -*- coding: utf-8 -*-
import zipfile
from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
def q(t): return "{%s}%s" % (W, t)

src = r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\src_draft.docx"
z = zipfile.ZipFile(src)
root = etree.fromstring(z.read("word/document.xml"))
body = root.find(q("body"))
paras = [c for c in body if c.tag == q("p")]

out = []
def w(s=""): out.append(str(s))

def dump(i):
    p = paras[i]
    w("=== P%d" % i)
    for k, r in enumerate([c for c in p if c.tag == q("r")]):
        kinds = []
        for c in r:
            ln = etree.QName(c).localname
            if ln == "t":
                kinds.append("t:%r" % (c.text or ""))
            elif ln == "tab":
                kinds.append("TAB")
            elif ln == "br":
                kinds.append("BR:%s" % c.get(q("type")))
            elif ln == "pict":
                kinds.append("PICT")
            elif ln == "rPr":
                col = c.find(q("color"))
                kinds.append("rPr(color=%s)" % (col.get(q("val")) if col is not None else None))
            else:
                kinds.append(ln)
        w("  r%d: %s" % (k, " | ".join(kinds)))
    w()

for i in [33, 34, 35, 36, 37, 38, 39, 40]:
    dump(i)

for i in [139, 166, 181, 225]:
    p = paras[i]
    w("=== P%d shape xml" % i)
    for sh in p.iter("{urn:schemas-microsoft-com:vml}shape"):
        s = etree.tostring(sh, encoding="unicode")
        w(s[:1400])
        w("---")
    w()

open(r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\probe26.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok", len(out))
