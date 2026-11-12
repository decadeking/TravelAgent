# -*- coding: utf-8 -*-
import zipfile
from lxml import etree
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
def q(t): return "{%s}%s" % (W, t)
z = zipfile.ZipFile(r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\src_draft.docx")
root = etree.fromstring(z.read("word/document.xml"))
body = root.find(q("body"))
paras = [c for c in body if c.tag == q("p")]

def is_red(r):
    rp = r.find(q("rPr"))
    if rp is None: return False
    c = rp.find(q("color"))
    return c is not None and (c.get(q("val")) or "").upper() == "FF0000"

targets = [74,75,76,79,80,81,102,103,104,107,108,109,110,111,113,114,120,121,127,129,132,133,138,142,143,157,158,162,163,167,168,169,178,179,180,191,192,193,208,221,224,234,244,257,258,260,261,270,277,278,297,308,324,325]
for i in targets:
    if i >= len(paras): continue
    p = paras[i]
    parts = []
    for r in p:
        if r.tag != q("r"): continue
        t = "".join(x.text or "" for x in r.findall(q("t")))
        parts.append(("R" if is_red(r) else "k", t[:26]))
    print(i, parts)
