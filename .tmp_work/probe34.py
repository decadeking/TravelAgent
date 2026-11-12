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
for i in [104, 105, 169, 171, 191, 196, 197, 208, 209, 121, 122, 135, 144, 153, 279, 308, 325]:
    x = etree.tostring(paras[i], encoding="unicode")
    x = re.sub(r' xmlns:[a-zA-Z0-9]+="[^"]*"', "", x)
    out.append("=== P%d\n%s\n" % (i, x[:1400]))
open(r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\probe34.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok")
