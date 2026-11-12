"""RAG 端到端探针：管理员上传文档 → 清洗 → 切片 → 向量化入库 → 检索命中 → 删除。

用真实运行时配置（当前已配 openai text-embedding-3-small / 1536 维），
验证「管理员配置的向量模型」在整套链路上确实生效。

用法：python scripts/probe_rag_upload.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
DOC = """丽江古城旅行要点

一、门票与开放时间
古城维护费 50 元，全天开放，四方街傍晚人最多。

二、玉龙雪山
大索道往返约 120 元，海拔 4506 米，需提前一天预约。

三、美食
腊排骨火锅人均 60 元，鸡豆凉粉 12 元一份。

- 1 -
"""


def main() -> None:
    # trust_env=False：绕开系统代理，避免本机 127.0.0.1 请求被代理劫持（会得到 502）
    with httpx.Client(base_url=BASE, timeout=180, trust_env=False) as c:
        login = c.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        print(f"[登录] status={login.status_code}")
        if login.status_code != 200:
            print("登录失败:", login.text[:300])
            return
        token = login.json()["data"]["access_token"]
        h = {"Authorization": f"Bearer {token}"}

        up = c.post("/api/media/upload_doc", headers=h, params={"city": "丽江"},
                    files={"file": ("probe_lijiang.txt", DOC.encode("utf-8"), "text/plain")})
        if up.status_code != 200:
            print("上传失败:", up.status_code, up.text[:200])
            return
        d = up.json()["data"]
        print(f"[上传] {d['title']} · 类型={d.get('file_type')} · 城市={d.get('city')}")
        print(f"[清洗] {d['clean']['raw_chars']} 字 → {d['clean']['clean_chars']} 字，"
              f"丢弃 {d['clean']['dropped_lines']} 行")
        print(f"[切片] 本文档 {d['chunks']} 块 · 全库 {d['total_chunks']} 块 · "
              f"向量库 {d['vector_backend']} · provider={d.get('embedding_provider')}")

        s = c.post("/api/admin/kb/search", headers=h,
                   params={"query": "丽江玉龙雪山大索道多少钱 海拔多少"})
        hits = s.json()["data"]["hits"]
        for hit in hits[:3]:
            print(f"[检索] score={hit['score']:.4f} title={hit['title']} "
                  f"text={hit['text'][:70]}…")

        kb = c.get("/api/admin/kb", headers=h).json()["data"]
        mine = [x for x in kb if x["title"] == d["title"]]
        print(f"[入库] 知识库现有 {len(kb)} 篇，其中本次上传 {len(mine)} 篇")

        # 保留用于演示：如需清理可取消下面注释
        for x in mine:
            r = c.delete(f"/api/admin/kb/{x['id']}", headers=h)
            print(f"[清理] 删除探针文档 #{x['id']} → {r.status_code}")

        print("\n端到端链路（清洗→切片→向量化→入库→检索）验证完成")


if __name__ == "__main__":
    main()
