from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from app.review_store import ReviewStore


OFFICIAL_CAPABILITIES = (
    "SCENIC_GRADE",
    "OFFICIAL_NAME",
    "TICKET",
    "RESERVATION",
    "CLOSURE",
    "HOLIDAY_HOURS",
    "CAPACITY",
    "ANNOUNCEMENT",
)


@dataclass(frozen=True)
class OfficialSourceSeed:
    source_id: str
    official_name: str
    province_name: str
    city_name: str
    scenic_grade: str | None
    website_url: str
    ticketing_url: str | None = None
    wechat_name: str | None = None
    mini_program_name: str | None = None
    max_daily_capacity: int | None = None
    adapter_kind: str = "DOCUMENT"
    capabilities: tuple[str, ...] = OFFICIAL_CAPABILITIES


OFFICIAL_SOURCE_SEEDS: tuple[OfficialSourceSeed, ...] = (
    OfficialSourceSeed(
        "dpm",
        "故宫博物院",
        "北京市",
        "北京市",
        "5A",
        "https://www.dpm.org.cn/",
        "https://ticket.dpm.org.cn/",
        "故宫博物院",
        "故宫博物院",
    ),
    OfficialSourceSeed(
        "badaling",
        "八达岭长城",
        "北京市",
        "北京市",
        "5A",
        "https://www.badaling.cn/website/pc/index.html",
        "https://ticket.badaling.cn/",
        "八达岭长城",
        "长城内外旅游",
    ),
    OfficialSourceSeed(
        "jiuzhai",
        "九寨沟风景名胜区",
        "四川省",
        "阿坝藏族羌族自治州",
        "5A",
        "https://www.jiuzhai.com/",
        wechat_name="九寨沟",
        mini_program_name="阿坝旅游网",
        max_daily_capacity=41000,
    ),
    OfficialSourceSeed(
        "huangshan",
        "黄山风景区",
        "安徽省",
        "黄山市",
        "5A",
        "https://hsgwh.huangshan.gov.cn/",
        "https://www.huangshan.com.cn/",
        "黄山",
        "黄山旅游官方平台",
    ),
    OfficialSourceSeed(
        "bmy",
        "秦始皇帝陵博物院",
        "陕西省",
        "西安市",
        "5A",
        "https://www.bmy.com.cn/",
        "https://bmy.albatrip.cn/",
        "秦始皇帝陵博物院",
        "兵马俑票务在线",
        65000,
    ),
    OfficialSourceSeed(
        "panda",
        "成都大熊猫繁育研究基地",
        "四川省",
        "成都市",
        "4A",
        "https://www.panda.org.cn/",
        "https://pw.panda.org.cn/login.jhtml",
        "成都大熊猫繁育研究基地",
        "成都大熊猫繁育研究基地",
        85000,
    ),
    OfficialSourceSeed(
        "west_lake",
        "杭州西湖风景名胜区",
        "浙江省",
        "杭州市",
        "5A",
        "https://westlake.hangzhou.gov.cn/",
        wechat_name="杭州西湖风景名胜区",
    ),
    OfficialSourceSeed(
        "shanghai_disney",
        "上海迪士尼度假区",
        "上海市",
        "上海市",
        None,
        "https://www.shanghaidisneyresort.com/zh-cn/",
        "https://www.shanghaidisneyresort.com/zh-cn/tickets/reservation/",
        "上海迪士尼度假区",
        "上海迪士尼度假区",
    ),
    OfficialSourceSeed(
        "sxhm",
        "陕西历史博物馆",
        "陕西省",
        "西安市",
        "4A",
        "https://www.sxhm.com/",
        wechat_name="陕西历史博物馆",
        mini_program_name="陕西历史博物馆票务系统",
    ),
    OfficialSourceSeed(
        "njmuseum",
        "南京博物院",
        "江苏省",
        "南京市",
        "4A",
        "https://www.njmuseum.com/",
        wechat_name="南京博物院",
        mini_program_name="南京博物院",
    ),
)


def initialize_official_directory(store: ReviewStore) -> None:
    verified_at = datetime.now(timezone.utc).isoformat()
    for seed in OFFICIAL_SOURCE_SEEDS:
        item = asdict(seed)
        item["verified_at"] = verified_at
        item["discovery_status"] = "VERIFIED"
        store.upsert_official_source(item)


def official_seed(source_id: str) -> OfficialSourceSeed | None:
    return next((item for item in OFFICIAL_SOURCE_SEEDS if item.source_id == source_id), None)


def match_official_seed(place_name: str) -> OfficialSourceSeed | None:
    normalized = _normalize(place_name)
    matches = [
        item
        for item in OFFICIAL_SOURCE_SEEDS
        if normalized in _normalize(item.official_name)
        or _normalize(item.official_name) in normalized
    ]
    return max(matches, key=lambda item: len(_normalize(item.official_name)), default=None)


def _normalize(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())
