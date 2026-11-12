# -*- coding: utf-8 -*-
import zipfile
from lxml import etree
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
def q(t): return "{%s}%s" % (W, t)
p = r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\src_draft.docx"
z = zipfile.ZipFile(p)
root = etree.fromstring(z.read("word/document.xml"))
body = root.find(q("body"))
tbls = [c for c in body if c.tag == q("tbl")]
out = []
out.append("TABLES %d" % len(tbls))
for ti, tb in enumerate(tbls):
    trs = tb.findall(q("tr"))
    out.append("--- TBL%d rows=%d" % (ti, len(trs)))
    for ri, tr in enumerate(trs):
        tcs = tr.findall(q("tc"))
        info = []
        for ci, tc in enumerate(tcs):
            ps = tc.findall(q("p"))
            txt = "".join("".join(t.text or "" for t in pp.iter(q("t"))) for pp in ps)
            info.append("c%d(np=%d)%s" % (ci, len(ps), txt[:24]))
        trh = tr.find(q("trPr"))
        h = ""
        if trh is not None and trh.find(q("trHeight")) is not None:
            h = trh.find(q("trHeight")).get(q("val"))
        out.append("  r%d h=%s | %s" % (ri, h, " || ".join(info)))
open(r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\tblstat.txt", "w", encoding="utf-8").write("\n".join(out))
# dump TBL0 xml
x = etree.tostring(tbls[0], encoding="unicode")
import re
x = re.sub(r' xmlns:[a-zA-Z0-9]+="[^"]*"', "", x)
open(r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\tbl0.xml", "w", encoding="utf-8").write(x)
x1 = etree.tostring(tbls[1], encoding="unicode")
x1 = re.sub(r' xmlns:[a-zA-Z0-9]+="[^"]*"', "", x1)
open(r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\tbl1.xml", "w", encoding="utf-8").write(x1)
print("ok")
