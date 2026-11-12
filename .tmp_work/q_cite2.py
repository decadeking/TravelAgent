# -*- coding: utf-8 -*-
import re, sys, zipfile
from lxml import etree

DOC = r"c:\Users\decade\.trae-cn\attachments\05611784-8d0b-4e58-b07a-bf861093552b_53571792-ecb0-48d5-9aac-9c5b0599f225_33成晓宇-湖南软件职业技术大学本科生毕业设计.docx"
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
sys.stdout.reconfigure(encoding="utf-8")
with zipfile.ZipFile(DOC) as z:
    root = etree.fromstring(z.read("word/document.xml"))
paras = root.findall(".//w:body/w:p", NS)
texts = ["".join(t.text or "" for t in p.findall(".//w:t", NS)) for p in paras]

# 各种括号形式的引注
pat = re.compile(r"[\[【(](\d{1,2})[\]】)]")
print("== 疑似引注（排除文献列表区） ==")
ref_start = None
for i, t in enumerate(texts):
    if re.match(r"^\s*参考文献", t):
        ref_start = i
for i, t in enumerate(texts):
    if ref_start and i >= ref_start:
        continue
    for m in pat.finditer(t):
        s, e = max(0, m.start() - 45), min(len(t), m.end() + 5)
        print(f"P{i} <{m.group(0)}> ...{t[s]}...{t[e]}")

print("\n== 参考文献条目 ==")
if ref_start is not None:
    for i in range(ref_start, min(ref_start + 25, len(texts))):
        t = texts[i].strip()
        if t:
            print(f"P{i}: {t[:130]}")
        if "致谢" in t:
            break
