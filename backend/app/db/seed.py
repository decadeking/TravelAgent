"""seed：初始化账号、知识库、旅行吧动态与示例行程（幂等，可重复执行）。"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.logging import get_logger
from ..common.security import hash_password
from .models import (
    Comment, ItineraryItem, KBDocument, Post, PostLike, Trip, TripDay, User, UserPreference,
)

logger = get_logger("seed")

DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo123"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"

_DATA = Path(__file__).resolve().parents[2] / "data"

_USERS = [
    ("demo", "旅行体验官", "user", "爱把行程排得刚刚好，也爱临时改主意。"),
    ("admin", "系统管理员", "admin", "负责内容审核与系统配置。"),
    ("chengzi", "橙子旅行", "user", "一年有 200 天在路上。"),
    ("azhe", "山野阿哲", "user", "徒步、雪山、荒野与星空。"),
    ("xiaolu", "背包客小鹿", "user", "穷游爱好者，专找小众秘境。"),
    ("laozhou", "摄影师老周", "user", "用镜头记录中国的光影。"),
]


def _img(prompt: str, size: str = "landscape_4_3") -> str:
    return ("https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image"
            f"?prompt={quote(prompt)}&image_size={size}")


_POSTS = [
    ("chengzi", "成都四日，慢下来的方式", "成都", "成都市 · 宽窄巷子",
     "在人民公园喝了一下午盖碗茶，看掏耳朵的师傅忙个不停。成都的好，是它不催你。",
     ["成都", "慢生活", "美食"],
     ["Chengdu Kuanzhai Alley traditional street with red lanterns at dusk, warm tones, travel photography",
      "Chengdu giant panda eating bamboo close up, soft morning light"]),
    ("azhe", "青城山的清晨雾气", "成都", "都江堰 · 青城山",
     "五点起床爬到上清宫，云海从脚边漫过来。道教名山，走前山就好。",
     ["青城山", "徒步", "云海"],
     ["Qingcheng Mountain misty forest temple in early morning, Daoist mountain, cinematic"]),
    ("laozhou", "故宫的光，只等一场雪", "北京", "北京 · 故宫博物院",
     "红墙白雪，角楼倒影。为这张照片在护城河边站了两个小时。",
     ["北京", "故宫", "雪景"],
     ["Forbidden City red wall covered with snow, Beijing winter, cinematic light, travel photography",
      "Forbidden City corner tower reflection in moat water at sunrise"]),
    ("chengzi", "长城日落 | 八达岭", "北京", "北京 · 八达岭",
     "下午四点上山，人少很多。下山时整条山脉都是金色的。",
     ["北京", "长城", "日落"],
     ["Great Wall of China Badaling at golden sunset, mountain ridges, epic landscape"]),
    ("xiaolu", "上海外滩的夜，怎么拍都不会腻", "上海", "上海 · 外滩",
     "从南京路一路走到外滩，江风很大。对岸的灯一盏盏亮起来。",
     ["上海", "外滩", "夜景"],
     ["Shanghai Bund skyline at night, Lujiazui skyline reflection over Huangpu river, cityscape"]),
    ("chengzi", "西湖十景，走完三景就值了", "杭州", "杭州 · 西湖",
     "苏堤春晓、断桥残雪、雷峰夕照。租了辆自行车环湖，骑了三个小时。",
     ["杭州", "西湖", "骑行"],
     ["West Lake Hangzhou Su Causeway spring morning, willow trees, mist, Chinese landscape"]),
    ("laozhou", "灵隐寺的香火与树影", "杭州", "杭州 · 灵隐寺",
     "飞来峰的造像有千年历史，阳光从树叶漏下来，石头上都是光斑。",
     ["杭州", "灵隐寺", "人文"],
     ["Lingyin Temple Hangzhou ancient Buddhist temple with incense smoke and sunlight through trees"]),
    ("azhe", "兵马俑，站在两千年前", "西安", "西安 · 秦始皇兵马俑",
     "一号坑的规模和排列远超照片。建议请讲解，不然只能看个热闹。",
     ["西安", "兵马俑", "历史"],
     ["Terracotta Army Xi'an pit full of soldiers, dramatic lighting, historical site photography"]),
    ("xiaolu", "大唐不夜城，越晚越好逛", "西安", "西安 · 大唐不夜城",
     "华灯初上，整条街都是盛唐的样子。各种表演免费看。",
     ["西安", "夜景", "盛唐"],
     ["Tang Dynasty themed pedestrian street at night, colorful lanterns, Xi'an", "Xi'an city wall illuminated at night"]),
    ("chengzi", "鼓浪屿，把时间交给海风", "厦门", "厦门 · 鼓浪屿",
     "轮渡上岛，万国建筑一栋接一栋。找个转角坐下听钢琴声。",
     ["厦门", "海岛", "文艺"],
     ["Gulangyu Island Xiamen colonial architecture with bougainvillea, seaside, sunny"]),
    ("laozhou", "环岛路骑行，一路都是海", "厦门", "厦门 · 环岛路",
     "租了辆单车从曾厝垵一路骑到白城沙滩，风是咸的。",
     ["厦门", "骑行", "海岸"],
     ["Xiamen Island Ring Road coastal cycling path with blue sea, palm trees, sunny day"]),
    ("azhe", "亚龙湾，冬天最该去的地方", "三亚", "三亚 · 亚龙湾",
     "北方零下，这里 25 度。海水蓝得不真实。",
     ["三亚", "海岛", "度假"],
     ["Sanya Yalong Bay tropical beach turquoise water white sand, palm trees, aerial view"]),
    ("xiaolu", "丽江古城的一米阳光", "丽江", "丽江 · 大研古城",
     "清晨的古城没什么人，石板路被露水打湿。晚上热闹得完全不同。",
     ["丽江", "古城", "慢生活"],
     ["Lijiang Old Town cobblestone street with canals and wooden houses, morning light, Yunnan"]),
    ("laozhou", "漓江晨雾，像一幅水墨", "桂林", "桂林 · 漓江",
     "六点的漓江，竹筏漂在雾里。二十年了，这张还是我最喜欢的。",
     ["桂林", "漓江", "山水"],
     ["Li River Guilin karst mountains with morning mist, bamboo raft, Chinese ink painting style"]),
]

_COMMENTS = [
    "太美了，已收藏，下个月就去！",
    "请问住的哪家酒店？求推荐～",
    "照片拍得真好，什么镜头？",
    "正好在做攻略，太有用了，谢谢分享！",
    "这个地方我去过，确实值得。",
    "预算大概多少呀？求个参考",
    "看完立刻订了机票哈哈",
    "请问几月份去最合适？",
]


async def _get_or_create_user(db: AsyncSession, username: str) -> User | None:
    return await db.scalar(select(User).where(User.username == username))


async def seed(db: AsyncSession) -> None:
    # ── 账号 ──
    for username, nickname, role, bio in _USERS:
        existing = await _get_or_create_user(db, username)
        if existing is None:
            pwd = ADMIN_PASSWORD if username == "admin" else DEMO_PASSWORD
            db.add(User(username=username, password_hash=hash_password(pwd),
                        nickname=nickname, role=role, bio=bio))
    await db.commit()

    demo = await _get_or_create_user(db, DEMO_USERNAME)
    if demo:
        pref_count = await db.scalar(
            select(func.count()).select_from(UserPreference)
            .where(UserPreference.user_id == demo.id))
        if not pref_count:
            db.add_all([
                UserPreference(user_id=demo.id, pref_key="avoid_hiking", pref_value="是"),
                UserPreference(user_id=demo.id, pref_key="culture", pref_value="是"),
            ])
        await db.commit()

    # ── 知识库（RAG 语料，DB 驱动） ──
    kb_count = await db.scalar(select(func.count()).select_from(KBDocument)) or 0
    if kb_count == 0:
        try:
            with open(_DATA / "knowledge_base.json", encoding="utf-8") as f:
                docs = json.load(f)
        except Exception:
            docs = []
        for d in docs:
            db.add(KBDocument(city=d.get("city", "通用"), title=d.get("title", ""),
                              content=d.get("content", ""), source="内置语料库"))
        await db.commit()
        logger.info("已初始化知识库", extra={"tool": f"kb_docs={len(docs)}"})

    # ── 旅行吧动态 ──
    post_count = await db.scalar(select(func.count()).select_from(Post)) or 0
    if post_count == 0:
        users = {u.username: u for u in (await db.scalars(select(User))).all()}
        for idx, (username, title, city, location, content, tags, prompts) in enumerate(_POSTS):
            author = users.get(username) or demo
            if author is None:
                continue
            post = Post(
                user_id=author.id, title=title, city=city, location=location,
                content=content,
                images=json.dumps([_img(p) for p in prompts], ensure_ascii=False),
                tags=json.dumps(tags, ensure_ascii=False),
                like_count=0, comment_count=0, collect_count=0,
                view_count=120 + idx * 37, status="published",
            )
            db.add(post)
            await db.flush()
            # 点赞（其他用户）
            others = [u for n, u in users.items() if u and u.id != author.id][:3]
            for u in others:
                db.add(PostLike(post_id=post.id, user_id=u.id))
            post.like_count = len(others)
            # 评论
            for j in range(2):
                cu = others[(idx + j) % len(others)] if others else author
                db.add(Comment(post_id=post.id, user_id=cu.id,
                               content=_COMMENTS[(idx + j) % len(_COMMENTS)]))
            post.comment_count = 2
        await db.commit()
        logger.info("已初始化旅行吧动态", extra={"tool": f"posts={len(_POSTS)}"})

    # ── 示例行程 ──
    if demo:
        trip_exists = await db.scalar(select(Trip).where(Trip.user_id == demo.id))
        if trip_exists is None:
            trip = Trip(user_id=demo.id, title="成都4日人文美食之旅", destination="成都",
                        days=4, budget=3000, status="confirmed", version=1)
            plan = [
                (1, "成都", "多云 20~28℃", [
                    ("morning", "大熊猫繁育研究基地", "nature", 55, 180),
                    ("afternoon", "武侯祠", "culture", 50, 120),
                    ("evening", "锦里古街", "culture", 0, 90),
                ]),
                (2, "成都", "晴 21~30℃", [
                    ("morning", "杜甫草堂", "culture", 50, 120),
                    ("afternoon", "宽窄巷子", "culture", 0, 120),
                    ("evening", "春熙路", "shopping", 0, 120),
                ]),
            ]
            for day_no, city, weather, items in plan:
                day = TripDay(day_no=day_no, city=city, weather_snapshot=weather)
                for seq, (slot, name, cat, cost, dur) in enumerate(items, start=1):
                    day.items.append(ItineraryItem(
                        seq=seq, time_slot=slot, poi_name=name, category=cat,
                        cost=cost, duration_min=dur))
                trip.day_list.append(day)
            db.add(trip)
            await db.commit()
            logger.info("已创建示例行程", extra={"event": "seed_trip"})
