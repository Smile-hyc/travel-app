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
    poi_id: str | None = None


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
        poi_id="B000A8UIN8",
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
        poi_id="B000A45467",
    ),
    OfficialSourceSeed(
        "summer_palace",
        "颐和园",
        "北京市",
        "北京市",
        "5A",
        "https://summerpalace.net.cn/",
        "https://yhy.yidyou.cn/",
        adapter_kind="DIRECTORY",
        capabilities=("SCENIC_GRADE", "OFFICIAL_NAME", "TICKET", "RESERVATION", "ANNOUNCEMENT"),
        poi_id="B000A7O1CU",
    ),
    OfficialSourceSeed(
        "beijing_zhongshan_park",
        "北京中山公园",
        "北京市",
        "北京市",
        None,
        "https://www.zhongshan-park.cn/",
        adapter_kind="DIRECTORY",
        capabilities=("OFFICIAL_NAME", "CLOSURE", "HOLIDAY_HOURS", "ANNOUNCEMENT"),
        poi_id="B000A840SB",
    ),
    OfficialSourceSeed(
        "beijing_jingshan_park",
        "北京市景山公园",
        "北京市",
        "北京市",
        None,
        "https://www.bjjspark.cn/",
        adapter_kind="DIRECTORY",
        capabilities=("OFFICIAL_NAME", "CLOSURE", "HOLIDAY_HOURS", "ANNOUNCEMENT"),
        poi_id="B000A7I1OL",
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
        poi_id="B00157AW8O",
    ),
    OfficialSourceSeed(
        "oriental_pearl",
        "东方明珠广播电视塔",
        "上海市",
        "上海市",
        "5A",
        "https://www.orientalpearltower.com/",
        adapter_kind="DIRECTORY",
        capabilities=("SCENIC_GRADE", "OFFICIAL_NAME", "TICKET", "RESERVATION", "ANNOUNCEMENT"),
        poi_id="B00150F6D6",
    ),
    OfficialSourceSeed(
        "shanghai_yuyuan",
        "上海豫园",
        "上海市",
        "上海市",
        None,
        "https://www.yugarden.com.cn/page/articleView/index.html",
        adapter_kind="DIRECTORY",
        capabilities=("OFFICIAL_NAME", "TICKET", "RESERVATION", "ANNOUNCEMENT"),
        poi_id="B00155MF55",
    ),
    OfficialSourceSeed(
        "shanghai_jingan_temple",
        "上海静安寺",
        "上海市",
        "上海市",
        None,
        "https://www.shjas.org/",
        adapter_kind="DIRECTORY",
        capabilities=("OFFICIAL_NAME", "CLOSURE", "HOLIDAY_HOURS", "ANNOUNCEMENT"),
        poi_id="B00154BDE9",
    ),
    OfficialSourceSeed(
        "tianjin_water_park",
        "天津水上公园",
        "天津市",
        "天津市",
        None,
        "https://csgl.tj.gov.cn/ywzt/ylgl/sggyjj/202504/t20250427_6918928.html",
        adapter_kind="GOVERNMENT_DIRECTORY",
        capabilities=("OFFICIAL_NAME", "ANNOUNCEMENT"),
        poi_id="B001605O2L",
    ),
    OfficialSourceSeed(
        "tianjin_tower",
        "天塔湖风景区",
        "天津市",
        "天津市",
        None,
        "https://towertj.net/",
        adapter_kind="DIRECTORY",
        capabilities=("OFFICIAL_NAME", "TICKET", "RESERVATION", "CLOSURE", "HOLIDAY_HOURS", "ANNOUNCEMENT"),
        poi_id="B00160CFPH",
    ),
    OfficialSourceSeed(
        "zhoudeng_memorial",
        "周恩来邓颖超纪念馆",
        "天津市",
        "天津市",
        None,
        "https://www.mzhoudeng.com/html/",
        adapter_kind="DIRECTORY",
        capabilities=("OFFICIAL_NAME", "RESERVATION", "CLOSURE", "HOLIDAY_HOURS", "ANNOUNCEMENT"),
        poi_id="B001609OZV",
    ),
    OfficialSourceSeed(
        "hongyan_zhou_mansion",
        "周公馆",
        "重庆市",
        "重庆市",
        None,
        "https://www.hongyanmuseum.cn/",
        adapter_kind="DIRECTORY",
        capabilities=("OFFICIAL_NAME", "RESERVATION", "CLOSURE", "HOLIDAY_HOURS", "ANNOUNCEMENT"),
        poi_id="B00170LAPL",
    ),
    OfficialSourceSeed(
        "chongqing_hongyadong",
        "洪崖洞民俗风貌区",
        "重庆市",
        "重庆市",
        None,
        "https://www.cq.gov.cn/zjcq/cycq/jplyxl/dsy/dsjp/202409/t20240905_13599455.html",
        adapter_kind="GOVERNMENT_DIRECTORY",
        capabilities=("OFFICIAL_NAME", "ANNOUNCEMENT"),
        poi_id="B0FFG8V7SH",
    ),
    OfficialSourceSeed(
        "chongqing_hongyadong_viewpoint",
        "洪崖洞夜景观景台",
        "重庆市",
        "重庆市",
        None,
        "https://www.cq.gov.cn/zjcq/cycq/jplyxl/dsy/dsjp/202409/t20240905_13599455.html",
        adapter_kind="GOVERNMENT_DIRECTORY",
        capabilities=("OFFICIAL_NAME", "ANNOUNCEMENT"),
        poi_id="B0FFG2D40O",
    ),
    OfficialSourceSeed(
        "chongqing_luohan_temple",
        "重庆罗汉寺",
        "重庆市",
        "重庆市",
        None,
        "https://chinabuddhism.com.cn/web/details/43515",
        adapter_kind="ASSOCIATION_DIRECTORY",
        capabilities=("OFFICIAL_NAME", "ANNOUNCEMENT"),
        poi_id="B001702CBC",
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
