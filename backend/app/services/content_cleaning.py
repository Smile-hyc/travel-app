from __future__ import annotations

import html
import re
from dataclasses import dataclass

from app.schemas.explore import PlaceSummary, ReviewSource


MIN_RELEVANCE_SCORE = 0.58
MAX_SHORT_SUMMARY_LENGTH = 240

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_CONTACT_RE = re.compile(
    r"(?:加|留|联系)?\s*(?:微信|vx|v信|小窗|私信|电话|手机号)"
    r"\s*[:：]?\s*[A-Za-z0-9_+\-]{5,}",
    re.IGNORECASE,
)
_SPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[\s·•,，。.!！?？()（）\-_/\\]", re.UNICODE)
_BRANCH_RE = re.compile(r"[（(][^）)]{0,24}(?:店|馆|院|景区|分店)?[）)]")
_WALKING_EXPERIENCE_RE = re.compile(
    r"步行(?!街)|走路|爬坡|台阶|腿酸|体力|不绕路|两万步|暴走|"
    r"全程.{0,16}(?:公里|km|小时|分钟)|\d+(?:\.\d+)?\s*(?:公里|km)",
    re.IGNORECASE,
)

PROMOTIONAL_MARKERS = (
    "商务合作",
    "广告",
    "团购链接",
    "返现",
    "私信领取",
    "加微信",
    "代订",
)

TAG_RULES: dict[str, tuple[str, ...]] = {
    "PHOTO": ("拍照", "出片", "机位", "摄影", "光线", "好拍", "大片", "草坪"),
    "QUEUE": ("排队", "人多", "拥挤", "客流", "等候"),
    "RESERVATION": ("预约", "抢票", "放票", "实名", "购票"),
    "WALKING": ("步行", "走路", "爬坡", "台阶", "腿酸", "体力"),
    "FOOD": ("好吃", "美食", "味道", "餐厅", "小吃"),
    "WORTH_IT": (
        "值得", "推荐", "必去", "好玩", "体验", "不感兴趣", "可以略过",
        "商业化严重", "破坏了", "不值得", "踩雷", "老少皆宜",
    ),
}

_CURATED_PLACE_ALIASES: dict[str, tuple[str, ...]] = {
    "东方明珠广播电视塔": ("东方明珠",),
    "上海四行仓库抗战纪念馆": ("四行仓库",),
    "福州路文化街": ("福州路",),
    "万国建筑博览群": ("外滩万国建筑", "万国建筑群", "万国建筑"),
    "天主教天津教区西开总堂": ("西开教堂", "西开总堂"),
    "小白楼1902欧式风情街": ("小白楼1902",),
    "洪崖洞民俗风貌区": ("洪崖洞",),
    "洪崖洞夜景观景台": ("洪崖洞夜景", "洪崖洞"),
    "重庆十八梯传统风貌区": ("十八梯",),
    "人民解放纪念碑": ("解放碑",),
    "十八梯观景台": ("十八梯",),
    "重庆朝天门广场": ("朝天门广场", "朝天门"),
}


@dataclass(frozen=True)
class CleanedReview:
    source: ReviewSource
    relevance_score: float
    short_summary: str
    tags: list[str]
    promotional: bool


def clean_review_sources(
    place: PlaceSummary,
    sources: list[ReviewSource],
    *,
    limit: int = 20,
) -> list[CleanedReview]:
    results: list[CleanedReview] = []
    seen_note_ids: set[str] = set()
    seen_fingerprints: set[str] = set()
    for source in sources:
        if source.deleted or not source.id.strip() or not _safe_source_url(source.url):
            continue
        note_id = source.id.removeprefix("xiaohongshu:").strip()
        if not note_id or note_id in seen_note_ids:
            continue
        title = normalize_ugc_text(source.title, limit=100)
        excerpt = normalize_ugc_text(source.excerpt or "", limit=MAX_SHORT_SUMMARY_LENGTH)
        combined = " ".join(part for part in (title, excerpt) if part)
        relevance = source.relevanceScore or compute_place_relevance(place, title, excerpt)
        if relevance < MIN_RELEVANCE_SCORE:
            continue
        fingerprint = _normalize_for_match(combined)[:160]
        if not fingerprint or fingerprint in seen_fingerprints:
            continue
        promotional = is_promotional(combined)
        # Pure acquisition advertisements are not useful experience evidence.
        if promotional and not any(keyword in combined for values in TAG_RULES.values() for keyword in values):
            continue
        summary = (
            f"{title}。{excerpt}"
            if title and excerpt and _normalize_for_match(title) not in _normalize_for_match(excerpt)
            else excerpt or title
        )
        short_summary = summary[:MAX_SHORT_SUMMARY_LENGTH]
        results.append(
            CleanedReview(
                source=source.model_copy(update={"title": title, "excerpt": excerpt or None}),
                relevance_score=round(min(1.0, relevance), 3),
                short_summary=short_summary,
                # Never attach a tag whose supporting words were truncated
                # from the evidence actually persisted and shown to users.
                tags=extract_experience_tags(short_summary, place_name=place.name),
                promotional=promotional,
            ),
        )
        seen_note_ids.add(note_id)
        seen_fingerprints.add(fingerprint)
        if len(results) >= max(1, min(limit, 50)):
            break
    return results


def normalize_ugc_text(value: str, *, limit: int = MAX_SHORT_SUMMARY_LENGTH) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]{1,200}>", " ", text)
    text = _URL_RE.sub(" ", text)
    text = _CONTACT_RE.sub(" ", text)
    text = "".join(character for character in text if character.isprintable())
    text = _SPACE_RE.sub(" ", text).strip(" ，,。.!！?？|-")
    return text[: max(1, limit)]


def compute_place_relevance(place: PlaceSummary, title: str, excerpt: str | None) -> float:
    haystack = _normalize_for_match(" ".join(filter(None, (title, excerpt))))
    exact_name = _normalize_for_match(place.name)
    base_name = _normalize_for_match(_BRANCH_RE.sub("", place.name))
    aliases = _place_aliases(place.name)
    score = 0.0
    if exact_name and exact_name in haystack:
        score += 0.72
    elif base_name and len(base_name) >= 3 and base_name in haystack:
        score += 0.58
    elif any(alias in haystack for alias in aliases):
        # Common note titles use short public names (for example "故宫") while
        # AMap keeps the formal POI name ("故宫博物院").
        score += 0.62
    location_tokens = {
        token
        for value in (place.cityName, place.districtName, place.provinceName)
        if value
        for token in _location_aliases(value)
    }
    location_matched = any(token and token in haystack for token in location_tokens)
    if location_matched:
        score += 0.16
    # Short names such as “小白楼” and “钟楼” collide across cities and even
    # with restaurants.  A name hit alone is not sufficient evidence that the
    # note describes this AMap POI; require the note to mention its city,
    # district or province as well.
    if exact_name and len(exact_name) <= 4 and not location_matched:
        score -= 0.28
    if any(token in haystack for token in ("攻略", "游览", "参观", "景点", "旅游", "打卡")):
        score += 0.08
    if any(marker in haystack for marker in ("同名", "不是", "避雷假店")):
        score -= 0.12
    if aliases and _has_conflicting_alias_prefix(haystack, aliases, location_tokens):
        score -= 0.22
    return round(max(0.0, min(1.0, score)), 3)


def extract_experience_tags(text: str, *, place_name: str | None = None) -> list[str]:
    result: list[str] = []
    for tag, keywords in TAG_RULES.items():
        if tag == "WALKING":
            matched = bool(_WALKING_EXPERIENCE_RE.search(text))
        else:
            matched = any(keyword in text for keyword in keywords)
        if not matched:
            continue
        # City-wide itineraries often mention a POI in the route and list food
        # or an opinion hundreds of characters later.  Those are not evidence
        # about food or value at this place.  Require proximity for the two
        # most context-sensitive tags.
        if place_name and tag == "WALKING" and any(
            marker in text for marker in ("咖啡", "餐厅", "人均", "营业时间")
        ) and not any(
            marker in text for marker in ("全程", "路线", "不绕路", "暴走", "走路")
        ):
            matched = False
        elif place_name and tag == "PHOTO":
            matched = _keyword_near_place(text, place_name, keywords, distance=90)
        elif place_name and tag == "QUEUE":
            matched = _queue_near_place(text, place_name, keywords)
        elif place_name and tag == "FOOD":
            matched = _food_near_place(text, place_name, keywords)
        elif place_name and tag == "WORTH_IT":
            matched = _worth_near_place(text, place_name, keywords)
        if matched:
            result.append(tag)
    return result


def is_promotional(text: str) -> bool:
    normalized = text.lower()
    return any(marker.lower() in normalized for marker in PROMOTIONAL_MARKERS)


def _safe_source_url(value: str) -> bool:
    return value.startswith("https://www.xiaohongshu.com/") or value.startswith(
        "https://xhslink.com/",
    )


def _normalize_for_match(value: str) -> str:
    return _PUNCT_RE.sub("", value).lower()


def _place_aliases(name: str) -> set[str]:
    normalized = _normalize_for_match(_BRANCH_RE.sub("", name))
    suffixes = (
        "博物院",
        "博物馆",
        "纪念馆",
        "风景名胜区",
        "文化旅游区",
        "旅游景区",
        "旅游区",
        "景区",
        "公园",
    )
    aliases = {
        normalized[: -len(suffix)]
        for suffix in suffixes
        if normalized.endswith(suffix) and len(normalized) - len(suffix) >= 2
    }
    aliases.update(
        _normalize_for_match(alias)
        for alias in _CURATED_PLACE_ALIASES.get(name, ())
    )
    return {alias for alias in aliases if len(alias) >= 2}


def _keyword_near_place(
    text: str,
    place_name: str,
    keywords: tuple[str, ...],
    *,
    distance: int,
) -> bool:
    normalized_text = _normalize_for_match(text)
    names = {_normalize_for_match(place_name), *_place_aliases(place_name)}
    name_positions = [
        normalized_text.find(name)
        for name in names
        if name and normalized_text.find(name) >= 0
    ]
    keyword_positions = [
        normalized_text.find(_normalize_for_match(keyword))
        for keyword in keywords
        if normalized_text.find(_normalize_for_match(keyword)) >= 0
    ]
    return any(
        abs(name_position - keyword_position) <= distance
        for name_position in name_positions
        for keyword_position in keyword_positions
    )


def _food_near_place(text: str, place_name: str, keywords: tuple[str, ...]) -> bool:
    normalized_text = _normalize_for_match(text)
    names = {_normalize_for_match(place_name), *_place_aliases(place_name)}
    normalized_keywords = {_normalize_for_match(keyword) for keyword in keywords}
    proximity_markers = ("附近", "周边", "对面", "门口", "旁边", "里面", "地铁站", "巷子", "地址")
    marker_pattern = "(?:" + "|".join(map(re.escape, proximity_markers)) + ")"
    for name in names:
        if not name or name not in normalized_text:
            continue
        name_pattern = re.escape(name)
        for keyword in normalized_keywords:
            if not keyword:
                continue
            keyword_pattern = re.escape(keyword)
            patterns = (
                rf"{name_pattern}.{{0,60}}{marker_pattern}.{{0,60}}{keyword_pattern}",
                rf"{keyword_pattern}.{{0,60}}{marker_pattern}.{{0,60}}{name_pattern}",
                rf"{marker_pattern}.{{0,40}}{name_pattern}.{{0,60}}{keyword_pattern}",
            )
            if any(re.search(pattern, normalized_text) for pattern in patterns):
                return True
    return False


def _queue_near_place(text: str, place_name: str, keywords: tuple[str, ...]) -> bool:
    """Exclude route copy such as “不排队吃美食” from POI crowd advice."""
    route_food_claim = bool(re.search(r"不排队.{0,16}(?:吃|美食|早点|餐厅)", text))
    for clause in re.split(r"[。！？!?；;\.\n]+", text):
        if re.search(r"不排队.{0,16}(?:吃|美食|早点|餐厅)", clause):
            continue
        if _keyword_near_place(clause, place_name, keywords, distance=65):
            return True
    return not route_food_claim and _keyword_near_place(
        text,
        place_name,
        keywords,
        distance=65,
    )


def _worth_near_place(text: str, place_name: str, keywords: tuple[str, ...]) -> bool:
    """Keep value judgements about the POI, not a route, photo or nearby dish."""
    names = {_normalize_for_match(place_name), *_place_aliases(place_name)}
    food_markers = ("好吃", "美食", "餐厅", "小吃", "米饭", "鸡排", "咖啡", "豆角", "茄子")
    photo_markers = ("航拍", "拍摄于", "机位", "成片")
    strong_markers = (
        "不感兴趣",
        "可以略过",
        "商业化严重",
        "破坏了",
        "不值得",
        "踩雷",
        "体验感",
    )
    for clause in re.split(r"[。！？!?；;\.\n]+", text):
        normalized_clause = _normalize_for_match(clause)
        if not any(name and name in normalized_clause for name in names):
            continue
        matched_keywords = [
            keyword
            for keyword in keywords
            if keyword in clause and not (keyword == "踩雷" and "不踩雷" in clause)
        ]
        if not matched_keywords:
            continue
        if any(
            marker in clause and not (marker == "踩雷" and "不踩雷" in clause)
            for marker in strong_markers
        ):
            return True
        if any(marker in clause for marker in food_markers + photo_markers):
            continue
        if _keyword_near_place(clause, place_name, tuple(matched_keywords), distance=55):
            return True
    # A concise source often puts the POI in the title and the judgement in
    # the next sentence.  Allow that short title→body span while rejecting a
    # nearby restaurant judgement or “recommended route, filmed near POI”.
    normalized_text = _normalize_for_match(text)
    for name in names:
        name_position = normalized_text.find(name)
        if name_position < 0:
            continue
        for keyword in keywords:
            if keyword == "踩雷" and "不踩雷" in text:
                continue
            keyword_position = normalized_text.find(_normalize_for_match(keyword))
            if keyword_position < 0 or abs(name_position - keyword_position) > 55:
                continue
            start = max(0, min(name_position, keyword_position) - 12)
            end = min(len(normalized_text), max(name_position, keyword_position) + 24)
            window = normalized_text[start:end]
            if any(_normalize_for_match(marker) in window for marker in food_markers):
                continue
            if keyword_position < name_position and any(
                _normalize_for_match(marker) in window for marker in photo_markers
            ):
                continue
            return True
    return False


def _location_aliases(value: str) -> set[str]:
    normalized = _normalize_for_match(value)
    aliases = {normalized}
    for suffix in ("特别行政区", "自治区", "自治州", "地区", "省", "市", "区", "县"):
        if normalized.endswith(suffix) and len(normalized) - len(suffix) >= 2:
            aliases.add(normalized[: -len(suffix)])
    return aliases


def _has_conflicting_alias_prefix(
    haystack: str,
    aliases: set[str],
    location_tokens: set[str],
) -> bool:
    valid_locations = {
        token.removesuffix(suffix)
        for token in location_tokens
        for suffix in ("市", "省", "自治区", "特别行政区")
        if token.endswith(suffix)
    } | location_tokens
    for alias in aliases:
        position = haystack.find(alias)
        if position < 2:
            continue
        prefix = haystack[max(0, position - 4) : position]
        if not any(token and prefix.endswith(token) for token in valid_locations):
            return True
    return False
