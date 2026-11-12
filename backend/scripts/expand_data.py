"""扩充本地数据：新增城市 POI + 更新知识库语料（幂等，按名称/标题去重）。

用法（backend 目录）：python scripts/expand_data.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")

DATA = Path(__file__).resolve().parents[1] / "data"

NEW_POI: dict[str, list[dict]] = {
    "重庆": [
        {"name": "洪崖洞", "category": "culture", "ticket": 0, "duration_min": 120,
         "rating": 4.6, "open_time": "全天开放（夜景最佳）", "tags": ["人文", "夜景", "免费"],
         "note": "吊脚楼式建筑群，夜间灯光像千与千寻，建议傍晚前往"},
        {"name": "解放碑", "category": "shopping", "ticket": 0, "duration_min": 90,
         "rating": 4.4, "open_time": "全天开放", "tags": ["购物", "免费"],
         "note": "重庆地标商圈，紧邻八一好吃街"},
        {"name": "长江索道", "category": "sightseeing", "ticket": 30, "duration_min": 40,
         "rating": 4.5, "open_time": "07:30-22:30", "tags": ["观光", "体验"],
         "note": "横跨长江的空中巴士，单程约 5 分钟，排队较久"},
        {"name": "磁器口古镇", "category": "culture", "ticket": 0, "duration_min": 150,
         "rating": 4.3, "open_time": "全天开放", "tags": ["人文", "美食", "免费"],
         "note": "嘉陵江畔古镇，陈麻花与毛血旺聚集"},
        {"name": "三峡博物馆", "category": "museum", "ticket": 0, "duration_min": 120,
         "rating": 4.6, "open_time": "09:00-17:00（周一闭馆）", "tags": ["博物馆", "免费"],
         "note": "需预约，了解三峡与重庆城市史的最佳去处"},
        {"name": "南山一棵树", "category": "nature", "ticket": 30, "duration_min": 90,
         "rating": 4.5, "open_time": "09:00-22:00", "tags": ["自然", "夜景"],
         "note": "俯瞰渝中半岛夜景的最佳观景台"},
    ],
    "三亚": [
        {"name": "亚龙湾", "category": "nature", "ticket": 0, "duration_min": 180,
         "rating": 4.7, "open_time": "全天开放", "tags": ["自然", "海边", "免费"],
         "note": "号称天下第一湾，沙质细白适合游泳"},
        {"name": "蜈支洲岛", "category": "nature", "ticket": 144, "duration_min": 300,
         "rating": 4.7, "open_time": "08:00-17:30", "tags": ["自然", "海岛", "潜水"],
         "note": "需乘船上岛，水上项目丰富，建议留一整天"},
        {"name": "天涯海角", "category": "sightseeing", "ticket": 68, "duration_min": 120,
         "rating": 4.2, "open_time": "07:30-18:00", "tags": ["观光", "海边"],
         "note": "标志性石刻，适合拍照留念"},
        {"name": "南山文化旅游区", "category": "culture", "ticket": 108, "duration_min": 240,
         "rating": 4.6, "open_time": "08:00-17:30", "tags": ["人文", "佛教"],
         "note": "108 米海上观音像，园区大建议乘电瓶车"},
        {"name": "第一市场", "category": "food", "ticket": 0, "duration_min": 120,
         "rating": 4.3, "open_time": "09:00-24:00", "tags": ["美食", "免费"],
         "note": "海鲜加工一条街，注意明码标价"},
        {"name": "鹿回头公园", "category": "nature", "ticket": 42, "duration_min": 90,
         "rating": 4.4, "open_time": "09:00-22:00", "tags": ["自然", "夜景"],
         "note": "俯瞰三亚湾与市区夜景"},
    ],
    "丽江": [
        {"name": "丽江古城", "category": "culture", "ticket": 0, "duration_min": 240,
         "rating": 4.6, "open_time": "全天开放", "tags": ["人文", "免费"],
         "note": "世界文化遗产，清晨人少适合拍照"},
        {"name": "玉龙雪山", "category": "nature", "ticket": 100, "duration_min": 300,
         "rating": 4.7, "open_time": "07:00-16:00", "tags": ["自然", "雪山"],
         "note": "海拔高需备氧气瓶，索道另收费，建议早出发"},
        {"name": "束河古镇", "category": "culture", "ticket": 0, "duration_min": 150,
         "rating": 4.4, "open_time": "全天开放", "tags": ["人文", "免费"],
         "note": "比丽江古城安静，适合慢逛与喝茶"},
        {"name": "拉市海", "category": "nature", "ticket": 0, "duration_min": 180,
         "rating": 4.1, "open_time": "08:00-18:00", "tags": ["自然", "湿地"],
         "note": "湿地观鸟与骑马，注意甄别低价团"},
        {"name": "蓝月谷", "category": "nature", "ticket": 0, "duration_min": 120,
         "rating": 4.6, "open_time": "08:00-17:00", "tags": ["自然", "湖泊"],
         "note": "玉龙雪山脚下，湖水呈蓝绿色，含在雪山票内"},
        {"name": "黑龙潭公园", "category": "nature", "ticket": 0, "duration_min": 90,
         "rating": 4.3, "open_time": "07:00-19:00", "tags": ["自然", "免费"],
         "note": "可拍雪山倒影"},
    ],
    "桂林": [
        {"name": "漓江", "category": "nature", "ticket": 215, "duration_min": 240,
         "rating": 4.8, "open_time": "08:00-14:00", "tags": ["自然", "游船"],
         "note": "桂林山水精华段，竹筏或游船，建议清晨出发"},
        {"name": "象鼻山", "category": "nature", "ticket": 55, "duration_min": 90,
         "rating": 4.5, "open_time": "06:30-19:30", "tags": ["自然", "地标"],
         "note": "桂林城徽，可远观或入园"},
        {"name": "阳朔西街", "category": "shopping", "ticket": 0, "duration_min": 180,
         "rating": 4.4, "open_time": "全天开放", "tags": ["购物", "美食", "免费"],
         "note": "阳朔最热闹的老街，夜晚酒吧与小吃集中"},
        {"name": "遇龙河", "category": "nature", "ticket": 0, "duration_min": 180,
         "rating": 4.7, "open_time": "08:00-17:00", "tags": ["自然", "漂流"],
         "note": "竹筏漂流比漓江更安静，田园风光"},
        {"name": "十里画廊", "category": "nature", "ticket": 0, "duration_min": 150,
         "rating": 4.5, "open_time": "全天开放", "tags": ["自然", "骑行", "免费"],
         "note": "适合租自行车或电动车游览"},
        {"name": "龙脊梯田", "category": "nature", "ticket": 80, "duration_min": 360,
         "rating": 4.7, "open_time": "全天开放", "tags": ["自然", "梯田"],
         "note": "距市区较远，需单独安排一天，日出云海最佳"},
    ],
}

NEW_KB: list[dict] = [
    {"city": "重庆", "title": "重庆游玩与交通要点（更新）",
     "content": "重庆是山城，导航距离与实际步行时间差距大，务必以地铁+步行为主，2 号线李子坝轻轨穿楼是网红点。洪崖洞夜景 19:30 后最佳，与千厮门大桥同框取景更好。长江索道建议线上购票减少排队。夏天酷热（常超 38℃），行程尽量安排在早晚，中午回酒店休息。火锅推荐解放碑、观音桥一带，微辣也很辣，可要求鸳鸯锅。三峡博物馆、白公馆、渣滓洞需预约，周一多数博物馆闭馆。"},
    {"city": "重庆", "title": "重庆门票与避坑提示（更新）",
     "content": "洪崖洞、解放碑、磁器口免费；长江索道单程 30 元、往返 40 元；南山一棵树 30 元；三峡博物馆免费需预约。避坑：不要相信洪崖洞附近「带你走捷径」的拉客；磁器口陈麻花排长队的多为网红店，本地人更认老字号；两江游船票分档多，注意看清是否含餐。"},
    {"city": "三亚", "title": "三亚海岛与季节提示（更新）",
     "content": "三亚最佳季节为 10 月至次年 4 月，5-9 月多雨且可能遇台风，出海项目易停航。蜈支洲岛需乘船上岛，门票+船票约 144 元，水上项目单独收费，建议留一整天。亚龙湾沙质最好适合游泳；三亚湾看日落；大东海离市区近。海鲜建议去第一市场自选加工，务必先问单价并复秤。防晒指数高，需 SPF50+ 与物理防晒并用。"},
    {"city": "三亚", "title": "三亚亲子与预算分配（更新）",
     "content": "亲子首选亚特兰蒂斯水世界或海昌梦幻不夜城，其次亚龙湾的酒店亲子配套。酒店是三亚预算大头，海棠湾与亚龙湾度假酒店普遍 800-2000 元/晚，市区酒店更便宜但需打车去海边。带小孩建议每天只安排 1 个主项目，避开正午暴晒。蜈支洲岛、南山文化旅游区等均需提前线上购票。"},
    {"city": "丽江", "title": "丽江古城与雪山要点（更新）",
     "content": "丽江古城免费开放，清晨 7-9 点人少、光线好，适合拍照；古城内石板路多，行李箱建议寄存改用背包。玉龙雪山门票 100 元，大索道另收约 120 元，需提前预约；海拔 4506 米，建议提前备氧气瓶，有高血压或心脏问题者谨慎。蓝月谷含在雪山景区内，湖水呈蓝绿色。束河古镇比大研古城安静，适合慢游。"},
    {"city": "丽江", "title": "丽江避坑与交通提示（更新）",
     "content": "拉市海「低价骑马+划船」一日游常见强制购物与额外收费，建议选正规平台并看清是否含餐含接送。丽江古城维护费现多为景区联票形式，按需购买。机场到古城约 40 分钟，可乘机场大巴或网约车。周边泸沽湖单程约 4 小时，需安排 2 天。"},
    {"city": "桂林", "title": "桂林漓江与阳朔线路（更新）",
     "content": "漓江精华段为桂林至阳朔，游船约 4 小时（票价约 215 元），竹筏漂流更贴近水面但受水位影响可能停运。阳朔西街夜晚最热闹，酒吧与小吃集中。遇龙河竹筏比漓江安静，田园风光更好。十里画廊适合租电动车。龙脊梯田距市区约 2 小时车程，需单独安排一天，5-6 月灌水期与 9-10 月金秋最佳。"},
    {"city": "桂林", "title": "桂林门票与美食提示（更新）",
     "content": "象鼻山 55 元、龙脊梯田 80 元、漓江游船约 215 元；阳朔西街、十里画廊免费。桂林米粉是本地早餐首选，卤菜粉约 6-10 元；阳朔啤酒鱼按斤计价，注意先确认重量与单价。雨季（4-6 月）漓江水位高可能影响漂流，出行前关注景区公告。"},
    {"city": "通用", "title": "出行前证件与预约清单（更新）",
     "content": "热门景区普遍实行实名预约：故宫、陕西历史博物馆、三峡博物馆、厦门大学等需提前 1-7 天在官方渠道预约，周一多为闭馆日。身份证、学生证（部分景区半价）、驾驶证（租车用）建议随身携带。高铁票预售期 15 天，节假日需抢票；机票提前 3-6 周价格更低。境外出行需检查护照有效期是否超 6 个月。"},
    {"city": "通用", "title": "天气与衣物打包建议（更新）",
     "content": "出发前 3 天查目的地天气并关注降水概率：雨天备防水外套与防滑鞋，海边备防晒与泳衣，高海拔地区（丽江、拉萨）备薄羽绒与氧气瓶，山区昼夜温差大需分层穿搭。常用药品建议带肠胃药、感冒药、创可贴与晕车药。充电宝、转换插头、离线地图提前准备好。"},
    {"city": "通用", "title": "预算分配与省钱技巧（更新）",
     "content": "一般行程中住宿与交通占预算 60% 以上，门票与餐饮弹性较大。省钱技巧：错峰出行（避开节假日与暑期）、住地铁沿线而非景区门口、提前网购景区联票、午餐在居民区解决、多人出行拼车分摊。免费景点往往体验不差，如西湖、外滩、宽窄巷子、象鼻山外围。"},
    {"city": "通用", "title": "带老人小孩的行程节奏（更新）",
     "content": "带小孩：每天主项目不超过 2 个，午间安排回酒店休息，优先亲子乐园、海洋馆、动物园，避免长时间登山与暴晒。带老人：控制步行量，景区内多用观光车与索道，避开高海拔与高强度徒步，行程留出充足缓冲时间，随身携带常用药与医保卡。"},
]


def main() -> None:
    poi_path = DATA / "poi.json"
    pois = json.loads(poi_path.read_text(encoding="utf-8"))
    added = 0
    for city, items in NEW_POI.items():
        if city in pois:
            continue
        pois[city] = items
        added += len(items)
    if added:
        poi_path.write_text(json.dumps(pois, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"poi.json: 新增 {added} 条，现有城市 {len(pois)} 个")

    kb_path = DATA / "knowledge_base.json"
    kb = json.loads(kb_path.read_text(encoding="utf-8"))
    titles = {d.get("title") for d in kb}
    n = 0
    for doc in NEW_KB:
        if doc["title"] in titles:
            continue
        kb.append(doc)
        titles.add(doc["title"])
        n += 1
    if n:
        kb_path.write_text(json.dumps(kb, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"knowledge_base.json: 新增 {n} 篇，现有 {len(kb)} 篇")


main()
