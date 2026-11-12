# -*- coding: utf-8 -*-
"""只读：列出上标 run + 打印 1.2/3.1/3.2 相关段落"""
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

print("===== 上标 run 内容 =====")
for i, p in enumerate(paras):
    sup = []
    for r in p.findall(".//w:r", NS):
        va = r.find("./w:rPr/w:vertAlign", NS)
        if va is not None and va.get("{%s}val" % NS["w"]) == "superscript":
            sup.append("".join(t.text or "" for t in r.findall(".//w:t", NS)))
    if sup:
        print(f"[P{i}] 上标={sup} | 全段={ptext(p)[:110]}")

print("\n===== 1.2 与 3.1/3.2 段落 =====")
for i, p in enumerate(paras):
    t = ptext(p).strip()
    if re.match(r"^1\.2|^1\.3|^3\.1 |^3\.2|^第2章", t) or ("朱宇豪" in t) or ("江志英" in t) or ("车万翔" in t) or ("ReAct" in t) or ("Lewis" in t) or ("Toolformer" in t) or ("TravelPlanner" in t) or ("ReWOO" in t) or ("核心实体包括" in t):
        print(f"[P{i}] {t}")
