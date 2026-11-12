"""切片策略：两级切片。

1. 先按结构切——标题（# / 第X部分 / 行首短句）、段落（空行）是天然边界；
2. 再限长——每块目标 300-500 token（中文约 380 字），相邻块保留约 10%-15%
   重叠（约 50 字），防止句子被拦腰截断。
每块附元数据：城市、标题、来源（source），供检索过滤与前端引用溯源。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Chunk:
    chunk_id: str
    text: str
    metadata: dict = field(default_factory=dict)


def _split_sentences(text: str) -> list[str]:
    """按中文标点切句，作为限长切分的最小单元。"""
    parts = re.split(r"(?<=[。！？；!?;\n])", text)
    return [p.strip() for p in parts if p and p.strip()]


def _is_heading(s: str) -> bool:
    return bool(re.match(r"^(#{1,6}\s+\S|第[一二三四五六七八九十]+[部章节]|[一二三四五六七八九十]+、)", s)) \
        or (0 < len(s) <= 20 and s.endswith(("：", ":")) and "。" not in s)


def _split_sections(text: str) -> list[tuple[str, str]]:
    """第一级：按结构切——标题行为边界，返回 [(小节标题, 小节正文)]。"""
    sections: list[tuple[str, str]] = []
    cur_title, buf = "", []
    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            continue
        if _is_heading(s):
            if buf:
                sections.append((cur_title, "\n".join(buf)))
                buf = []
            cur_title = s.lstrip("#").strip("：: ")
        else:
            buf.append(s)
    if buf:
        sections.append((cur_title, "\n".join(buf)))
    return sections


def chunk_text(text: str, *, doc_id: str, city: str = "通用", title: str = "",
               source: str = "", chunk_size: int = 380, overlap: int = 50) -> list[Chunk]:
    """两级切片：先按结构（标题/段落）切，再对超长小节限长+重叠。"""
    chunks: list[Chunk] = []
    idx = 0

    def _emit(section_title: str, body: str) -> None:
        nonlocal idx
        sentences = _split_sentences(body)
        buf = ""
        for sent in sentences:
            if len(buf) + len(sent) > chunk_size and buf:
                chunks.append(Chunk(
                    chunk_id=f"{doc_id}#{idx}",
                    text=buf.strip(),
                    metadata={"doc_id": doc_id, "city": city,
                              "title": section_title or title,
                              "doc_title": title, "source": source},
                ))
                idx += 1
                buf = buf[-overlap:] if overlap else ""
            buf += sent
        if buf.strip():
            chunks.append(Chunk(
                chunk_id=f"{doc_id}#{idx}",
                text=buf.strip(),
                metadata={"doc_id": doc_id, "city": city,
                          "title": section_title or title,
                          "doc_title": title, "source": source},
            ))
            idx += 1

    sections = _split_sections(text)
    if not sections:
        _emit("", text)
        return chunks
    for sec_title, body in sections:
        _emit(sec_title, body)
    return chunks


def chunk_documents(docs: list[dict], *, chunk_size: int = 380,
                    overlap: int = 50) -> list[Chunk]:
    """docs: [{city,title,content,source}] → 全部块。"""
    out: list[Chunk] = []
    for i, d in enumerate(docs):
        out.extend(chunk_text(
            d.get("content", ""), doc_id=f"doc{i}",
            city=d.get("city", "通用"), title=d.get("title", ""),
            source=d.get("source", ""),
            chunk_size=chunk_size, overlap=overlap,
        ))
    return out
