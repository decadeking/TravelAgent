"""头像与图片资源落盘：把「路径文字 / data URL / 外链」统一变成后端资源文件夹里的真实文件。

用途：
1. 给所有已有用户生成/分配头像文件（随机风景照优先，失败则用内置矢量头像），
   并把 users.avatar 写成后端调用路径 /api/media/{id}；
2. 顺带把 user.cover 与 posts.images 里遗留的 data: URL、外链迁移落盘。

用法（backend 目录下）：
    python scripts/seed_avatars.py            # 补全缺头像的用户 + 迁移遗留图片
    python scripts/seed_avatars.py --force    # 重新随机分配所有用户头像
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import sys

import httpx
from sqlalchemy import func, select

sys.path.insert(0, ".")

from app.db.models import Media, Post, User  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services.media_service.router import (  # noqa: E402
    materialize_image, media_url, store_bytes,
)

# 矢量头像配色（与前端预设一致，保证与管理端/用户端观感统一）
_PRESETS = [
    ("#6366f1", "#3b82f6"), ("#0ea5e9", "#22c55e"), ("#f59e0b", "#ef4444"),
    ("#8b5cf6", "#ec4899"), ("#14b8a6", "#0ea5e9"), ("#f43f5e", "#f97316"),
]


def _avatar_svg(name: str) -> tuple[bytes, str]:
    """按用户名生成确定性矢量头像（渐变底 + 首字），返回 (字节, 配色索引)。"""
    seed = int(hashlib.md5((name or "traveler").encode()).hexdigest()[:8], 16)
    c1, c2 = _PRESETS[seed % len(_PRESETS)]
    initial = (name or "旅").strip()[:1].upper()
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" '
        f'viewBox="0 0 256 256"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{c1}"/><stop offset="1" stop-color="{c2}"/>'
        f'</linearGradient></defs><rect width="256" height="256" rx="72" fill="url(#g)"/>'
        f'<text x="128" y="164" font-size="116" fill="#ffffff" text-anchor="middle" '
        f'font-family="system-ui,-apple-system,Segoe UI,sans-serif">{initial}</text></svg>'
    )
    return svg.encode("utf-8"), c2


async def _fetch_photo(seed: str) -> tuple[bytes, str] | None:
    """取一张随机风景照（picsum 免费图源）；失败返回 None。"""
    url = f"https://picsum.photos/seed/{seed}/256/256"
    try:
        resp = httpx.get(url, timeout=12.0, follow_redirects=True,
                         headers={"User-Agent": "TravelAgent/1.0"})
        if resp.status_code != 200:
            return None
        data = resp.content
        if not data or len(data) > 2 * 1024 * 1024:
            return None
        return data, (resp.headers.get("content-type") or "image/jpeg").split(";")[0]
    except Exception:
        return None


async def main(force: bool = False) -> None:
    async with SessionLocal() as db:
        users = (await db.scalars(select(User))).all()
        photos = svg_used = kept = 0
        for u in users:
            current = (u.avatar or "").strip()
            if current.startswith("/api/media/") and not force:
                kept += 1
                continue
            seed = u.username or str(u.id)
            got = await _fetch_photo(seed)
            if got:
                data, mime = got
                row = await store_bytes(db, data, mime=mime, owner_id=u.id,
                                        kind="avatar", source_url=f"picsum:seed={seed}")
                photos += 1
            else:
                svg, _ = _avatar_svg(u.nickname or u.username or str(u.id))
                row = await store_bytes(db, svg, mime="image/svg+xml", owner_id=u.id,
                                        kind="avatar", source_url="builtin:gradient")
                svg_used += 1
            u.avatar = media_url(row.id)
            await db.commit()
        print(f"头像处理完成：随机照片 {photos} 个 · 矢量头像 {svg_used} 个 · 已就绪跳过 {kept} 个")

        # 遗留图片迁移：data: URL / 外链 → 后端资源文件夹
        fixed_posts = fixed_covers = 0
        for p in (await db.scalars(select(Post))).all():
            try:
                urls = json.loads(p.images or "[]")
            except Exception:
                continue
            if not isinstance(urls, list) or not urls:
                continue
            if all(u.startswith("/api/media/") for u in urls if isinstance(u, str)):
                continue
            new_urls: list[str] = []
            changed = False
            for url in urls:
                if not isinstance(url, str) or not url.strip():
                    continue
                if url.startswith("/api/media/"):
                    new_urls.append(url)
                    continue
                row = await materialize_image(db, url, owner_id=p.user_id, kind="image")
                if row is None:
                    continue                      # 无法落盘（本地路径/不可下载）→ 丢弃
                new_urls.append(media_url(row.id))
                changed = True
            if changed:
                p.images = json.dumps(new_urls, ensure_ascii=False)
                await db.commit()
                fixed_posts += 1

        for u in (await db.scalars(select(User))).all():
            cover = (u.cover or "").strip()
            if not cover or cover.startswith("/api/media/"):
                continue
            row = await materialize_image(db, cover, owner_id=u.id, kind="image")
            if row is not None:
                u.cover = media_url(row.id)
                await db.commit()
                fixed_covers += 1

        total = await db.scalar(select(func.count()).select_from(Media)) or 0
        print(f"图片迁移完成：帖子 {fixed_posts} 条 · 背景图 {fixed_covers} 个 · 媒体库共 {total} 个文件")

    from app.db.session import engine
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main(force="--force" in sys.argv))
