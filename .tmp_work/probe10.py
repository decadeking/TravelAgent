# -*- coding: utf-8 -*-
import zipfile
SRC = r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\src_draft.docx"
z = zipfile.ZipFile(SRC)
out = []
for h in ("word/header1.xml", "word/header2.xml", "word/header3.xml"):
    x = z.read(h).decode("utf-8")
    out.append("=" * 20 + " " + h + " " + str(len(x)))
    out.append(x)
z.close()
open(r"c:\Users\decade\Desktop\TravelAgent\.tmp_work\p10.txt", "w", encoding="utf-8").write("\n".join(out))
print("ok")
