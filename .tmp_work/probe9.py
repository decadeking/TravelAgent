# -*- coding: utf-8 -*-
import zipfile, re, os
SRC = r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\src_draft.docx"
z = zipfile.ZipFile(SRC)
names = z.namelist()
print("=== media ===")
for n in names:
    if n.startswith("word/media/"):
        print(n, z.getinfo(n).file_size)
print("=== document rels (image) ===")
rels = z.read("word/_rels/document.xml.rels").decode("utf-8")
for m in re.finditer(r'<Relationship[^>]*/>', rels):
    s = m.group(0)
    if "image" in s:
        print(s)
print("=== content types ===")
ct = z.read("[Content_Types].xml").decode("utf-8")
print(ct[:2000])
print("=== headers/footers media ===")
for n in names:
    if "_rels" in n and ("header" in n or "footer" in n):
        print("--", n)
        t = z.read(n).decode("utf-8")
        for m in re.finditer(r'<Relationship[^>]*/>', t):
            if "image" in m.group(0):
                print("   ", m.group(0))
try:
    from PIL import Image
    import io
    print("PIL OK")
    for p in [r"C:\Users\decade\AppData\Local\Temp\fig\01.png", r"C:\Users\decade\AppData\Local\Temp\fig\02.png",
              r"C:\Users\decade\AppData\Local\Temp\fig\03.png", r"C:\Users\decade\AppData\Local\Temp\fig\04.png",
              r"C:\Users\decade\AppData\Local\Temp\shots\s1.png", r"C:\Users\decade\AppData\Local\Temp\shots\s2.png",
              r"C:\Users\decade\AppData\Local\Temp\shots\s3.png", r"C:\Users\decade\AppData\Local\Temp\shots\s4.png",
              r"C:\Users\decade\AppData\Local\Temp\shots\s5.png", r"C:\Users\decade\AppData\Local\Temp\shots\ui.png",
              r"c:\Users\decade\Desktop\TravelAgent\diagrams\01-系统用例图.png",
              r"c:\Users\decade\Desktop\TravelAgent\diagrams\02-系统功能模块图.png",
              r"c:\Users\decade\Desktop\TravelAgent\diagrams\03-系统业务流程图.png",
              r"c:\Users\decade\Desktop\TravelAgent\diagrams\04-系统ER图.png"]:
        im = Image.open(p)
        print(os.path.basename(p), im.size, im.mode)
except Exception as e:
    print("PIL ERR", e)
# also show pict embed ids
doc = z.read("word/document.xml").decode("utf-8")
for m in re.finditer(r'r:embed="(rId\d+)"', doc):
    print("embed", m.group(1))
z.close()
