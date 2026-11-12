# -*- coding: utf-8 -*-
import re
p = r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\addref_unpacked\word\document.xml"
xml = open(p, encoding="utf-8").read()
keys = ["朱宇豪", "江志英", "车万翔", "ReAct", "检索增强生成", "Toolformer",
        "TravelPlanner", "ReWOO", "概念模型设计", "前后端分离"]
# 找到包含正文关键词的所有 <w:t> 文本
for m in re.finditer(r"<w:t(?: [^>]*)?>([^<]*)</w:t>", xml):
    t = m.group(1)
    for k in keys:
        if k in t:
            print("KEY", k, "->", t[:80])
            break
