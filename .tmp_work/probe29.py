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
for ri, tr in enumerate(t.findall(q("tr"))):
    for ci, tc in enumerate(tr.findall(q("tc"))):
        w("row%d c%d" % (ri, ci))
        for pj, p in enumerate(tc.findall(q("p"))):
            w("   p%d %r" % (pj, "".join(x.text or "" for x in p.iter(q("t")))))
w()
for ti in [0, 1]:
    w("TBL%d row0 cell runs:" % ti)
    tr = tbls[ti].findall(q("tr"))[0]
    for ci, tc in enumerate(tr.findall(q("tc"))):
        for p in tc.findall(q("p")):
            w("  c%d %r" % (ci, "".join(x.text or "" for x in p.iter(q("t")))))
    w("TBL%d row1:" % ti)
    tr = tbls[ti].findall(q("tr"))[1]
    for ci, tc in enumerate(tr.findall(q("tc"))):
        for p in tc.findall(q("p")):
            w("  c%d %r" % (ci, "".join(x.text or "" for x in p.iter(q("t")))))

open(r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\probe29.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok", len(out))
