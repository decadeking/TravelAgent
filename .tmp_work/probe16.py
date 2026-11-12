# -*- coding: utf-8 -*-
import zipfile
from lxml import etree

SRC = r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\src_draft.docx"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
def q(t): return "{%s}%s" % (W, t)

z = zipfile.ZipFile(SRC)
root = etree.fromstring(z.read("word/document.xml"))
body = root.find(q("body"))
paras = [c for c in body if c.tag == q("p")]

out = []
for i in (139, 158, 160, 166, 181, 191, 210, 211, 221, 222, 223, 225, 234, 235, 243, 244, 246, 254, 140):
    p = paras[i]
    runs = p.findall(q("r"))
    out.append("P%d  runs=%d" % (i, len(runs)))
    for j, r in enumerate(runs):
        t = "".join(x.text or "" for x in r.iter(q("t")))
        has_pict = r.find(".//" + q("pict")) is not None
        has_draw = r.find(".//" + q("drawing")) is not None
        rid = None
        shp = r.find(".//" + "{urn:schemas-microsoft-com:vml}shape")
        if shp is not None:
            rid = shp.get("{%s}id" % R)
        out.append("    r%d pict=%s drawing=%s rid=%s text=%r" % (j, has_pict, has_draw, rid, t[:60]))
    out.append("")
open(r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\p16.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok")
