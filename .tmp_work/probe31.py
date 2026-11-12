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
for i in range(70, 82):
    s = etree.tostring(paras[i], encoding="unicode")
    s = s.replace('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"', "")
    out.append("=== P%d len=%d" % (i, len(s)))
    out.append(s[:2500])
    out.append("")

open(r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\probe31.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok")
