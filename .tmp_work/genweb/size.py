# -*- coding: utf-8 -*-
import struct, os
DIAG = r"c:\Users\decade\Desktop\TravelAgent\diagrams"
SHOT = r"c:\Users\decade\AppData\Local\Temp\shots"
def png_size(p):
    with open(p, "rb") as f:
        d = f.read(33)
    w, h = struct.unpack(">II", d[16:24])
    return w, h
files = ["01-系统用例图.png","02-系统功能模块图.png","03-系统业务流程图.png","04-系统ER图.png"]
for f in files:
    print(f, png_size(os.path.join(DIAG, f)))
for i in range(1,6):
    print("s%d.png"%i, png_size(os.path.join(SHOT, "s%d.png"%i)))
