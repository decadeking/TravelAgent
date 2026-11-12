# -*- coding: utf-8 -*-
"""pass2: 媒体替换 + 页眉标题 + 图题注 + 清理空白说明段。基于 _unz 直接改后重打包。"""
import os, sys, shutil, zipfile, copy
from lxml import etree
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from docutil import *

WORK = r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\_unz"
OUT = r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\out_pass2.docx"
DIAG = r"c:\Users\decade\Desktop\TravelAgent\diagrams"
SHOT = r"c:\Users\decade\AppData\Local\Temp\shots"
DOC = os.path.join(WORK, "word", "document.xml")

parser = etree.XMLParser(remove_blank_text=False)
root = etree.parse(DOC, parser).getroot()
body = root.find("{%s}body" % W)

# 页眉：替换首个 text run 为新题目
HEAD_TITLE = "基于FastAPI和Vue3的交互式旅行规划智能体的设计与实现"
for hn in ["header1.xml", "header2.xml", "header3.xml"]:
    hp = os.path.join(WORK, "word", hn)
    if not os.path.exists(hp):
        continue
    hr = etree.parse(hp, parser).getroot()
    trs = [r for r in hr.iter("{%s}r" % W) if r.find("{%s}t" % W) is not None]
    if trs:
        first = trs[0]
        t = first.find("{%s}t" % W)
        t.text = HEAD_TITLE
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        # 删除其余 text run
        for r in trs[1:]:
            r.getparent().remove(r)
    with open(hp, "wb") as f:
        f.write(etree.tostring(hr, xml_declaration=True, encoding="UTF-8", standalone=True))

# 图题注更新（按文本定位段落）
CAPTION = {
    "图4.1 系统主页面": "图4.1 首页与行程列表页面",
    "图 4.3 发布招领信息页面截图": "图4.2 行程生成页面",
    "图 4.4 物品详情留言页面截图": "图4.3 行程详情与评论页面",
    "图 4.5 管理员信息审核页面截图": "图4.4 内容审核与用户管理页面",
    "图 4.6 数据统计可视化大屏截图": "图4.5 工具调用监控与数据统计页面",
}
def all_paras():
    return [c for c in body if c.tag == "{%s}p" % W]
for p in all_paras():
    txt = "".join(p.itertext()).strip()
    for old, new in CAPTION.items():
        if txt == old or txt.strip().startswith(old):
            set_para(p, new)
            break

# 删除残留红/格式说明空段（clean_red 后剩空 run 或仅 whitespace 的段）
# 规则：text 全空白且没有 pict 的段落，跨大区域删除——但保留封面/目录结构。
# 稳妥起见，只删出现在正文区(索引>100)且文本为空的段落，且其 pPr 有 outlineLvl(标题)保留。
paras = all_paras()
# 分节保护：含 sectPr 的段落是分节符，绝不能删
def has_sectpr(p):
    return p.find(".//{%s}sectPr" % W) is not None or p.find("{%s}sectPr" % W) is not None

# 定位"目录"之后的正文起始索引，只清理其后的空说明段
start = None
for i, p in enumerate(paras):
    if "目  录" in "".join(p.itertext()):
        start = i
        break

removed = 0
for p in list(paras):
    txt = "".join(p.itertext()).replace("\t", "").strip()
    has_pict = any(sh is not None for sh in p.iter("{%s}pict" % W))
    has_field = any(x is not None for x in p.findall(".//{%s}fldChar" % W))
    if has_pict or has_field or has_sectpr(p):
        continue
    # 只清理正文区（目录之后）的纯空段，且该段不含图片/分节
    if txt == "" or txt in ("\uf0b7", "•"):
        idx = all_paras().index(p)
        if start is None or idx > start:
            body.remove(p)
            removed += 1
            paras = all_paras()
print("removed blank paras", removed)

# 删除全空/无效表格（清空内容后没有有效数据的表）
tbls = [c for c in body if c.tag == "{%s}tbl" % W]
for tb in list(tbls):
    cells_text = "".join(tb.itertext()).strip()
    if cells_text == "":
        body.remove(tb)
        print("removed empty table")

# 重新打包
# 先压缩（在内存 zip 重建，media 用新图）
tmpzip = r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\_media_map.txt"
# media 映射：文档内 rId -> 文件名已在关系文件中；这里直接按文件名替换
media_map = {
    "image2.png": os.path.join(DIAG, "01-系统用例图.png"),
    "image3.png": os.path.join(DIAG, "02-系统功能模块图.png"),
    "image4.png": os.path.join(DIAG, "03-系统业务流程图.png"),
    "image5.png": os.path.join(DIAG, "04-系统ER图.png"),
    "image6.png": os.path.join(SHOT, "s1.png"),
    "image7.png": os.path.join(SHOT, "s2.png"),
    "image8.png": os.path.join(SHOT, "s3.png"),
    "image9.png": os.path.join(SHOT, "s4.png"),
    "image10.png": os.path.join(SHOT, "s5.png"),
}

if os.path.exists(OUT):
    os.remove(OUT)
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    for folder, _, files in os.walk(WORK):
        for fn in files:
            fp = os.path.join(folder, fn)
            arc = os.path.relpath(fp, WORK).replace("\\", "/")
            if arc in media_map and os.path.exists(media_map[arc]):
                z.write(media_map[arc], arc)
            else:
                z.write(fp, arc)

print("out_pass2 written")
