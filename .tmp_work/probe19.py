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

IDX = [103,107,110,113,114,117,120,121,122,123,124,125,126,
       129,132,133,138,142,143,147,152,157,159,161,162,163,167,168,169,170,171,
       179,180,192,193,194,208,209,221,222,224,234,244,
       258,259,260,261,262,270,278,279,284,325,326,327,298]

def a(el, name, attr="val"):
    if el is None: return ""
    e = el.find(q(name))
    if e is None: return ""
    v = e.get(q(attr))
    return "%s" % (v if v is not None else "")

def desc(p):
    ppr = p.find(q("pPr"))
    if ppr is None:
        return "NO-PPR"
    parts = []
    if ppr.find(q("pStyle")) is not None: parts.append("style=" + a(ppr, "pStyle"))
    sp = ppr.find(q("spacing"))
    if sp is not None:
        parts.append("sp[" + ",".join("%s=%s" % (etree.QName(k).localname, v) for k, v in sp.attrib.items()) + "]")
    ind = ppr.find(q("ind"))
    if ind is not None:
        parts.append("ind[" + ",".join("%s=%s" % (etree.QName(k).localname, v) for k, v in ind.attrib.items()) + "]")
    if ppr.find(q("jc")) is not None: parts.append("jc=" + a(ppr, "jc"))
    if ppr.find(q("outlineLvl")) is not None: parts.append("olvl=" + a(ppr, "outlineLvl"))
    if ppr.find(q("numPr")) is not None: parts.append("numPr")
    runs = p.findall(q("r"))
    rs = []
    for r in runs:
        rp = r.find(q("rPr"))
        sz = a(rp, "sz") if rp is not None else ""
        ea = ""
        if rp is not None:
            rf = rp.find(q("rFonts"))
            if rf is not None: ea = rf.get(q("eastAsia")) or ""
        rs.append("%s/%s" % (sz, ea))
    return " ".join(parts) + "  runs=%d[%s]" % (len(runs), " ".join(rs))

out = []
for i in IDX:
    t = "".join(x.text or "" for x in paras[i].iter(q("t")))
    out.append("P%-4d %s\n      %r" % (i, desc(paras[i]), t[:70]))
open(r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\p19.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok")
