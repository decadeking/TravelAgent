# -*- coding: utf-8 -*-
import zipfile
from lxml import etree

SRC = r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\src_draft.docx"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
def q(t): return "{%s}%s" % (W, t)

z = zipfile.ZipFile(SRC)
root = etree.fromstring(z.read("word/document.xml"))
body = root.find(q("body"))
tbls = [c for c in body if c.tag == q("tbl")]
out = []
out.append("tables=%d" % len(tbls))
s = etree.tostring(tbls[0], pretty_print=True, encoding="unicode")
# strip namespaces decl noise
import re
s = re.sub(r'\sxmlns:[a-zA-Z0-9]+="[^"]*"', "", s)
out.append(s)
open(r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\p18.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok")
