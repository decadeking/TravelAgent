# -*- coding: utf-8 -*-
import zipfile, re
from lxml import etree
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
def q(t): return "{%s}%s" % (W, t)
p = r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\src_draft.docx"
z = zipfile.ZipFile(p)
root = etree.fromstring(z.read("word/document.xml"))
body = root.find(q("body"))
paras = [c for c in body if c.tag == q("p")]
out = []
for i in [111, 139, 158, 160, 166, 181, 211, 225, 235, 246, 255]:
    pp = paras[i]
    runs = [r for r in pp if r.tag == q("r")]
    info = []
    for ri, r in enumerate(runs):
        has = r.find(q("pict")) is not None
        t = "".join(x.text or "" for x in r.iter(q("t")))
        info.append("r%d pict=%s t=%r" % (ri, has, t[:30]))
    out.append("=== P%d pPr=%s" % (i, etree.tostring(pp.find(q("pPr")), encoding="unicode") if pp.find(q("pPr")) is not None else None))
    out.append("  runs: " + " | ".join(info))
    for r in runs:
        pic = r.find(q("pict"))
        if pic is not None:
            x = etree.tostring(r, encoding="unicode")
            x = re.sub(r' xmlns:[a-zA-Z0-9]+="[^"]*"', "", x)
            out.append("  RUNXML: " + x)
open(r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\probe35.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok")
