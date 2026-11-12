"""原料清洗探针：验证不同文件类型分别经过什么清洗，并核对切片效果。

覆盖：
- txt（含控制字符、页码行、多余空行、GBK 编码）
- md（标题层级 + 列表）
- docx（段落 + 表格；WPS 另存的 .docx 同格式）
- pdf（含跨页重复页眉页脚与页码行）
- 脏数据文档（清洗后有效字符不足 → 拒绝入库）
并对清洗结果做两级切片，打印分块数与首块内容。

用法：python scripts/probe_cleaning.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, ".")

_DEMO_DIR = Path(__file__).resolve().parent / "_cleaning_demo"


def _minimal_pdf(pages: list[list[str]]) -> bytes:
    """手工构造一个带文本层的极简多页 PDF（ASCII 内容，便于 pdfplumber 抽取）。"""
    objs: list[bytes] = []
    n_pages = len(pages)
    kids = " ".join(f"{3 + i * 2} 0 R" for i in range(n_pages))
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode())
    for i, lines in enumerate(pages):
        content = ["BT", "/F1 12 Tf", "72 760 Td"]
        for j, ln in enumerate(lines):
            if j:
                content.append("0 -18 Td")
            content.append(f"({ln}) Tj")
        content.append("ET")
        stream = "\n".join(content).encode()
        objs.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Contents {4 + i * 2} 0 R /Resources << /Font << /F1 100 0 R >> >> >>".encode())
        objs.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
                    + stream + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for idx, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{idx} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(out)
    size = len(objs) + 1
    out += f"xref\n0 {size}\n".encode() + b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n").encode()
    return bytes(out)


def _build_files() -> dict[str, bytes]:
    """构造五份测试文件。"""
    txt = (
        "成都熊猫基地攻略\r\n"
        "\x0c\n"
        "一、门票与开放时间\n"
        "门票 55 元，开放时间 07:30-18:00，建议早上前往。\n"
        "- 1 -\n"
        "\n\n\n"
        "二、交通\n"
        "地铁 3 号线熊猫大道站下车，转景区接驳车。\n"
        "第 2 页\n"
        "三、温馨提示\n孩子们上午更活跃，中午后多回室内。\n"
    )
    md = (
        "# 杭州西湖骑行一日游\n\n"
        "## 路线\n"
        "- 断桥残雪 → 白堤 → 平湖秋月\n"
        "- 苏堤春晓 → 花港观鱼\n\n"
        "## 门票\n景区免费，游船 55 元/人。\n"
    )
    dirty = "   \n- 1 -\n\n    \n"
    return {"clean_demo.txt": txt.encode("utf-8"), "clean_demo_gbk.txt": txt.encode("gb18030"),
            "clean_demo.md": md.encode("utf-8"), "dirty_demo.txt": dirty.encode("utf-8")}


def _build_docx() -> bytes:
    from docx import Document

    doc = Document()
    doc.add_heading("西安三日游要点", level=1)
    doc.add_paragraph("兵马俑建议上午前往，避开人流高峰。")
    doc.add_paragraph("城墙骑行约 2 小时，可看日落。")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "景点"
    table.cell(0, 1).text = "门票"
    table.cell(1, 0).text = "兵马俑"
    table.cell(1, 1).text = "120 元"
    import io
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def main() -> None:
    from app.services.agent_service.rag.chunker import chunk_documents
    from app.services.media_service.parsers import clean_text, parse_document

    _DEMO_DIR.mkdir(exist_ok=True)
    files = _build_files()
    files["clean_demo.docx"] = _build_docx()
    # PDF：两页，每页首行都是重复页眉，末行是页码
    files["clean_demo.pdf"] = _minimal_pdf([
        ["Xian Travel Guide", "Terracotta Army ticket 120 CNY", "Open 08:30-17:00", "- 1 -"],
        ["Xian Travel Guide", "City Wall bike ride about 2 hours", "Best at sunset", "- 2 -"],
    ])

    print("=" * 66)
    for name, raw in files.items():
        (_DEMO_DIR / name).write_bytes(raw)
        res = parse_document(name, raw)
        if not res["ok"]:
            print(f"■ {name:<18} 拒绝：{res['error']}")
            continue
        c = res["clean"]
        print(f"■ {name:<18} 类型={res['kind']:<5} {res['meta']}")
        print(f"   清洗：{c['raw_chars']} 字 / {c['raw_lines']} 行 → "
              f"{c['clean_chars']} 字 / {c['clean_lines']} 行；"
              f"丢弃行 {c['dropped_lines']}（页眉页脚 {c['header_footer_removed']}）")
        preview = res["text"].replace("\n", " / ")[:110]
        print(f"   清洗后：{preview}")

    print("=" * 66)
    print("两级切片（380 字 / 重叠 50）效果：")
    yielded = [f for f in files if f.endswith((".txt", ".md", ".docx", ".pdf"))]
    docs = []
    for name in yielded:
        res = parse_document(name, files[name])
        if res["ok"]:
            docs.append({"city": "通用", "title": name, "content": res["text"],
                         "source": f"probe:{name}"})
    chunks = chunk_documents(docs, chunk_size=380, overlap=50)
    print(f"   共 {len(chunks)} 块；示例：")
    for ck in chunks[:3]:
        print(f"   - {ck.chunk_id} city={ck.metadata['city']} source={ck.metadata['source']} "
              f"len={len(ck.text)} text={ck.text[:50]}…")

    print("=" * 66)
    print("PDF 页眉/页脚识别（3 页以上才启用，这里演示判定逻辑）：")
    page_texts = [
        "成都旅行手册\n第一天 熊猫基地\n门票 55 元\n- 1 -",
        "成都旅行手册\n第二天 都江堰\n门票 80 元\n- 2 -",
        "成都旅行手册\n第三天 青城山\n门票 80 元\n- 3 -",
    ]
    cleaned, stats = clean_text("\n\n".join(page_texts), page_texts=page_texts)
    print(f"   识别并剔除页眉/页脚行 {stats['header_footer_removed']} 个，"
          f"丢弃行 {stats['dropped_lines']} 行")
    print("   清洗后：" + " / ".join(cleaned.split("\n")))

    print("=" * 66)
    print(f"演示文件已写入 {_DEMO_DIR}（可删）")


if __name__ == "__main__":
    main()
