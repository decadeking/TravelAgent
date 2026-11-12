# -*- coding: utf-8 -*-
"""提取 docx 正文中的 [n] 引注位置与参考文献列表（只读，不修改）"""
import re, sys, zipfile
from lxml import etree

DOC = r"c:\Users\decade\.trae-cn\attachments\05611784-8d0b-4e58-b07a-bf861093552b_53571792-ecb0-48d5-9aac-9c5b0599f225_33成晓宇-湖南软件职业技术大学本科生毕业设计.docx"
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

sys.stdout.reconfigure(encoding="utf-8")
with zipfile.ZipFile(DOC) as z:
    root = etree.fromstring(z.read("word/document.xml"))

paras = root.findall(".//w:body/w:p", NS)
texts = ["".join(t.text or "" for t in p.findall(".//w:t", NS)) for p in paras]

# 1) 正文中的 [数字] 引注
print("== 正文引注 ==")
pat = re.compile(r"\[(\d{1,2})\]")
for i, t in enumerate(texts):
    for m in pat.finditer(t):
        s, e = max(0, m.start() - 40), m.end()
        print(f"P{i} [{m.group(1)}] ...{texts[i][s:e]}")

# 2) 参考文献列表
print("\n== 参考文献 ==")
started = False
for i, t in enumerate(texts):
    if "参考文献" in t and len(t) < 10:
        started = True
        continue
    if started:
        if "致谢" in t and len(t) < 10:
            break
        if t.strip():
            print(f"{t.strip()[:120]}")
