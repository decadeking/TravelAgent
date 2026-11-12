# -*- coding: utf-8 -*-
import zipfile
from lxml import etree
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PIC = "http://schemas.openxmlformats.org/drawingml/2006/picture"
P = "http://schemas.openxmlformats.org/package/2006/relationships"
z = zipfile.ZipFile(r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\out_docxjs.docx")
media = [n for n in z.namelist() if n.startswith("word/media/")]
print("media count:", len(media), media)
body = etree.fromstring(z.read("word/document.xml")).find("{%s}body" % W)
paras = body.findall(".//{%s}p" % W)
tbls = body.findall(".//{%s}tbl" % W)
imgs = body.findall(".//{%s}blip" % A)
print("paras:", len(paras), "tables:", len(tbls), "images(blip):", len(imgs))
txt = "".join(body.itertext())
# 检查关键内容是否出现
for kw in ["智能旅行", "FastAPI", "LangGraph", "Table3.1", "致谢", "参考文献", "ReAct"]:
    pass
def cnt(s): return txt.count(s)
print("智能旅行:", cnt("智能旅行"), "FastAPI:", cnt("FastAPI"), "LangGraph:", cnt("LangGraph"))
print("表3.1 用户表:", cnt("用户表"), "致谢:", cnt("致谢"), "参考文献:", cnt("参考文献"))
print("code marker /auth/login:", cnt("/auth/login"))
