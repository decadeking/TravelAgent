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
for i in (181, 211):
    out.append("=" * 10 + " P%d" % i)
    out.append(etree.tostring(paras[i], pretty_print=True, encoding="unicode"))
open(r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\p17.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok")
