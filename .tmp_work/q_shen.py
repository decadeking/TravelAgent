# -*- coding: utf-8 -*-
"""在附件 docx 里查找 SHEN / 参考文献列表（只读）"""
import glob, re, sys, zipfile
from lxml import etree

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
sys.stdout.reconfigure(encoding="utf-8")

files = glob.glob(r"c:\Users\decade\.trae-cn\attachments\*\*.docx")
for f in files:
    try:
        with zipfile.ZipFile(f) as z:
            root = etree.fromstring(z.read("word/document.xml"))
    except Exception as e:
        print("SKIP", f, e)
        continue
    paras = root.findall(".//w:body/w:p", NS)
    texts = ["".join(t.text or "" for t in p.findall(".//w:t", NS)) for p in paras]
    hits = [(i, t) for i, t in enumerate(texts) if "SHEN" in t.upper()]
    if hits:
        print("\n###", f)
        for i, t in hits:
            print(f"[P{i}] {t[:200]}")
        print("---- 参考文献区 ----")
        start = next((i for i, t in enumerate(texts) if re.fullmatch(r"\s*参考文献", t)), None)
        if start:
            for i in range(start, min(start + 30, len(texts))):
                s = texts[i].strip()
                if s:
                    print(f"[P{i}] {s[:160]}")
                if s.startswith("致谢"):
                    break
