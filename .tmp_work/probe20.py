# -*- coding: utf-8 -*-
import zipfile, re
from lxml import etree

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
SRC = r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\src_draft.docx"


def q(t):
    return W + t


def txt(p):
    return "".join(t.text or "" for t in p.iter(q("t")))


z = zipfile.ZipFile(SRC)
root = etree.fromstring(z.read("word/document.xml"))
body = root.find(q("body"))
paras = [c for c in body if c.tag == q("p")]

out = []
for i in (74, 77, 78, 100, 101, 335):
    out.append("=" * 20 + " P%d " % i + "=" * 20)
    x = etree.tostring(paras[i], encoding="unicode")
    x = re.sub(r'\sxmlns:?[a-zA-Z0-9]*="[^"]*"', "", x)
    x = re.sub(r'\sw14:paraId="[^"]*"', "", x)
    out.append(x)

out.append("\n\n########## HEADERS ##########")
for n in z.namelist():
    if re.match(r"word/header\d*\.xml", n):
        out.append("=" * 20 + " " + n + " " + "=" * 20)
        h = etree.fromstring(z.read(n))
        hx = etree.tostring(h, encoding="unicode")
        hx = re.sub(r'\sxmlns:?[a-zA-Z0-9]*="[^"]*"', "", hx)
        out.append(hx)

with open(r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\p20.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("ok")
