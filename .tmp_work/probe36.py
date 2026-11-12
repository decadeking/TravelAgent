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

targets = list(range(121, 127)) + list(range(135, 138)) + list(range(144, 147)) + \
          list(range(148, 152)) + list(range(153, 156)) + list(range(279, 284)) + [200, 201, 202]

for i in targets:
    p = paras[i]
    ppr = p.find(q("pPr"))
    num = ppr is not None and ppr.find(q("numPr")) is not None
    numtxt = ""
    if num:
        np = ppr.find(q("numPr"))
        il = np.find(q("ilvl")); ni = np.find(q("numId"))
        numtxt = "ilvl=%s numId=%s" % (il.get(q("val")) if il is not None else None,
                                       ni.get(q("val")) if ni is not None else None)
    runs = []
    for r in p:
        if r.tag != q("r"):
            continue
        t = "".join(x.text or "" for x in r.findall(q("t")))
        rp = r.find(q("rPr"))
        sz = None
        if rp is not None:
            s = rp.find(q("sz"))
            if s is not None: sz = s.get(q("val"))
        runs.append((repr(t[:26]), sz))
    print("P%d numPr=%s %s | %s" % (i, num, numtxt, runs))
