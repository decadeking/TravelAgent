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
def w(s=""): out.append(str(s))

targets = [121,122,123,124,125,126,127,135,136,137,144,145,146,148,149,150,151,153,154,155,
           178,257,279,280,281,282,283,325,326,327,102,107,208,221,224,234,244,261,169,170,171]
for i in targets:
    p = paras[i]
    ppr = p.find(q("pPr"))
    num = ppr.find(q("numPr")) if ppr is not None else None
    ns = etree.tostring(num, encoding="unicode") if num is not None else "-"
    pprs = etree.tostring(ppr, encoding="unicode") if ppr is not None else "-"
    pprs = pprs.replace(' xmlns:w="%s"' % W, "")
    w("=== P%d numPr=%s" % (i, ns))
    w("  pPr=" + pprs[:600])
    for k, r in enumerate([r for r in p if r.tag == q("r")]):
        kinds = [etree.QName(c).localname for c in r]
        txt = "".join(t.text or "" for t in r.findall(q("t")))
        w("   r%d %s %r" % (k, kinds, txt[:80]))
    w()

w("=== page breaks ===")
for i, p in enumerate(paras):
    for br in p.iter(q("br")):
        if br.get(q("type")) == "page":
            w("P%d has page br" % i)
w("=== sectPr in paragraphs ===")
for i, p in enumerate(paras):
    if p.find(q("pPr")) is not None and p.find(q("pPr")).find(q("sectPr")) is not None:
        w("P%d has sectPr" % i)

w("=== TBL2 cells ===")
tbls = [c for c in body if c.tag == q("tbl")]
t = tbls[2]
for ri, tr in enumerate(t.findall(q("tr"))):
    for ci, tc in enumerate(tr.findall(q("tc"))):
        ps = tc.findall(q("p"))
        w("row%d c%d np=%d" % (ri, ci, len(ps)))
        for pj, p in enumerate(ps):
            w("   p%d %r" % (pj, "".join(x.text or "" for x in p.iter(q("t")))))

w("=== body child tail ===")
for c in list(body)[-6:]:
    w(etree.QName(c).localname)

open(r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\probe25.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok", len(out))
