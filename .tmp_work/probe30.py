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
for i in [5, 6, 8, 9, 10, 11, 12, 74, 75, 76, 79, 80, 81, 169, 170, 171, 308, 331, 333]:
    p = paras[i]
    runs = [c for c in p if c.tag == q("r")]
    out.append("=== P%d  runs=%d" % (i, len(runs)))
    for k, r in enumerate(runs):
        seg = []
        for c in r:
            ln = etree.QName(c).localname
            if ln == "t":
                seg.append("t:%r" % (c.text or ""))
            elif ln == "tab":
                seg.append("TAB")
            elif ln == "br":
                seg.append("BR")
            elif ln == "fldChar":
                seg.append("FLD:%s" % c.get(q("fldCharType")))
            elif ln == "instrText":
                seg.append("INSTR:%r" % (c.text or ""))
            elif ln == "pict":
                seg.append("PICT")
        out.append("  r%d: %s" % (k, " | ".join(seg)))
    out.append("")

open(r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\probe30.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok", len(out))
