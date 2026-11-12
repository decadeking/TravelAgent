"""文档解析与「原料清洗」：把 pdf / wps(docx) / txt / md 变成可入库的纯文本。

流程：识别类型 → 抽取文本 → 清洗（去控制字符、折叠空行、去页眉页脚/页码）→
交回调用方写入知识库并重建向量索引。

依赖（均已在 requirements 中）：
- pdfplumber   : PDF 文本层抽取（按页）
- python-docx  : OOXML（.docx；WPS 另存的 .docx 同格式，可直接解析）

不支持旧版二进制 .doc：提示用户另存为 .docx / .txt 后再上传。
"""
from __future__ import annotations

import io
import re
from pathlib import Path

# 扩展名 → 类型
EXT_KIND = {
    ".txt": "txt", ".md": "md", ".markdown": "md", ".log": "txt", ".csv": "txt",
    ".pdf": "pdf", ".docx": "docx", ".doc": "doc",
}
SUPPORTED_HINT = "支持 PDF、Word/WPS（.docx）、TXT、Markdown"

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")     # 保留 \t(09) \n(0a)
_PAGE_NO = re.compile(r"^\s*(?:[-—–]?\s*(?:第\s*)?\d{1,4}\s*(?:页|/\s*\d+)?\s*[-—–]?)\s*$")


def detect_kind(filename: str, mime: str = "") -> str:
    ext = Path(filename or "").suffix.lower()
    if ext in EXT_KIND:
        return EXT_KIND[ext]
    mime = (mime or "").lower()
    if mime == "application/pdf":
        return "pdf"
    if "wordprocessingml" in mime or mime == "application/msword":
        return "docx" if "wordprocessingml" in mime else "doc"
    if mime.startswith("text/"):
        return "txt"
    return ""


def _decode(raw: bytes) -> tuple[str, str]:
    """按常见中文编码顺序尝试解码，返回 (文本, 编码)。"""
    for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk", "big5"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8(replace)"


def _extract_pdf(raw: bytes) -> tuple[str, dict]:
    import pdfplumber
    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    text = "\n\n".join(pages)
    return text, {"pages": len(pages), "page_texts": pages}


def _extract_docx(raw: bytes) -> tuple[str, dict]:
    from docx import Document
    doc = Document(io.BytesIO(raw))
    parts = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
    # 表格内容一并抽取（攻略文档常见「门票/开放时间」表格）
    tables = 0
    for table in doc.tables:
        tables += 1
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text and c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts), {"paragraphs": len(doc.paragraphs), "tables": tables}


def clean_text(text: str, *, page_texts: list[str] | None = None) -> tuple[str, dict]:
    """原料清洗：返回 (干净文本, 统计)。

    - 去除控制字符，统一换行；
    - 逐行 strip，丢弃「页码」形态的装饰行；
    - PDF 场景：跨页重复的首/末行视为页眉页脚，直接剔除；
    - 折叠 3 行以上连续空行为 1 行空行（保留段落边界）。
    """
    raw = text or ""
    raw_chars, raw_lines = len(raw), raw.count("\n") + 1
    normalized = _CTRL.sub("", raw).replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.strip() for ln in normalized.split("\n")]

    dropped = 0

    def _is_page_no(s: str) -> bool:
        return bool(s) and bool(_PAGE_NO.match(s)) and len(s) <= 12

    # 页眉页脚：统计各页首/末行出现次数，出现 >= 一半页数的短行判为页眉页脚
    header_footer: set[str] = set()
    if page_texts and len(page_texts) >= 3:
        from collections import Counter
        counter: Counter = Counter()
        for pt in page_texts:
            rows = [r.strip() for r in (pt or "").split("\n") if r.strip()]
            if not rows:
                continue
            for cand in {rows[0], rows[-1]}:
                if len(cand) <= 40:
                    counter[cand] += 1
        threshold = max(2, len(page_texts) // 2)
        header_footer = {s for s, c in counter.items() if c >= threshold}

    out: list[str] = []
    for ln in lines:
        if not ln:
            out.append("")
            continue
        if _is_page_no(ln) or ln in header_footer:
            dropped += 1
            continue
        out.append(ln)

    # 折叠多余空行
    folded: list[str] = []
    blank = 0
    for ln in out:
        if ln == "":
            blank += 1
            if blank >= 2:
                dropped += 1
                continue
        else:
            blank = 0
        folded.append(ln)
    cleaned = "\n".join(folded).strip()
    stats = {
        "raw_chars": raw_chars, "clean_chars": len(cleaned),
        "raw_lines": raw_lines, "clean_lines": cleaned.count("\n") + 1 if cleaned else 0,
        "dropped_lines": dropped, "header_footer_removed": len(header_footer),
    }
    return cleaned, stats


def parse_document(filename: str, raw: bytes, mime: str = "") -> dict:
    """解析并清洗文档；失败时返回 {ok: False, error: ...}。"""
    kind = detect_kind(filename, mime)
    if not kind:
        return {"ok": False, "error": f"暂不支持该文件类型，{SUPPORTED_HINT}"}
    if kind == "doc":
        return {"ok": False,
                "error": "暂不支持旧版 .doc（二进制格式），请用 WPS/Word 另存为 .docx 或 .txt 后上传"}
    if not raw:
        return {"ok": False, "error": "文件为空"}
    try:
        if kind == "pdf":
            text, meta = _extract_pdf(raw)
        elif kind == "docx":
            text, meta = _extract_docx(raw)
        else:
            text, enc = _decode(raw)
            text, meta = text, {"encoding": enc}
    except Exception as exc:
        return {"ok": False, "error": f"文档解析失败：{exc}"}

    page_texts = meta.pop("page_texts", None)
    cleaned, clean_stats = clean_text(text, page_texts=page_texts)
    if len(cleaned.strip()) < 10:
        return {"ok": False, "error": "未能从文档中提取到有效文本（可能是扫描件或纯图片 PDF）"}
    return {"ok": True, "kind": kind, "text": cleaned, "meta": meta, "clean": clean_stats}
