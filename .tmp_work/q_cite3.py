# -*- coding: utf-8 -*-
"""只读提取：正文中的 [n] 引注位置 + 参考文献条目"""
import re, sys, zipfile
from lxml import etree

DOC = sys.argv[1]
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
sys.stdout.reconfigure(encoding="utf-8")

with zipfile.ZipFile(DOC) as z:
    root = etree.fromstring(z.read("word/document.xml"))

paras = root.findall(".//w:body/w:p", NS)

def ptext(p):
    return "".join(t.text or "" for t in p.findall(".//w:t", NS))

texts = [ptext(p) for p in paras]

ref_start = None
thanks_start = None
for i, t in enumerate(texts):
    s = t.strip()
    if re.fullmatch(r"参考文献", s) and ref_start is None:
        ref_start = i
    if re.fullmatch(r"致谢", s) and ref_start is not None and thanks_start is None:
        thanks_start = i

print("TOTAL PARAS", len(texts), "ref_start", ref_start, "thanks_start", thanks_start)

print("\n===== 参考文献条目 =====")
if ref_start is not None:
    end = thanks_start if thanks_start else len(texts)
    for i in range(ref_start + 1, end):
        t = texts[i].strip()
        if t:
            print(f"[P{i}] {t}")

print("\n===== 正文引注（[n] 或 上标数字） =====")
pat = re.compile(r"[\[［【(（](\d{1,2})[\]］】)）]")
end_scan = ref_start if ref_start else len(texts)
for i in range(end_scan):
    t = texts[i]
    hits = list(pat.finditer(t))
    if hits:
        for m in hits:
            a, b = max(0, m.start() - 50), min(len(t), m.end() + 6)
            print(f"[P{i}] <<{m.group(0)}>> ...{t[a:b]}...")
