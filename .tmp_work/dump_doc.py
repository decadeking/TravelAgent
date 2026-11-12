# 只读探查：按段落导出 docx 正文，便于逐段分析文风与 AIGC 风险
import sys
from pathlib import Path
import docx

src = Path(sys.argv[1])
out = Path(sys.argv[2])

doc = docx.Document(str(src))
lines = []
total_chars = 0
for i, p in enumerate(doc.paragraphs):
    text = p.text.strip()
    if not text:
        continue
    style = p.style.name if p.style is not None else ""
    total_chars += len(text)
    lines.append(f"[{i}] <{style}> ({len(text)}字) {text}")

out.write_text("\n".join(lines), encoding="utf-8")
print("paragraphs:", len(doc.paragraphs), "non-empty:", len(lines), "chars:", total_chars)
print("tables:", len(doc.tables))
