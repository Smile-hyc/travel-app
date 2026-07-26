from dataclasses import dataclass


@dataclass(frozen=True)
class AmapCategory:
    code: str
    keyword: str
    type_codes: str


AMAP_CATEGORY_MAPPING: dict[str, AmapCategory] = {
    "scenic": AmapCategory("scenic", "景点", "110000"),
    "museum": AmapCategory(
        "museum",
        "博物馆",
        "140100|140200|140400|140500|140600|140700",
    ),
    "food": AmapCategory("food", "美食", "050000"),
    "drink": AmapCategory("drink", "饮品", "050500|050600|050700|050800"),
    "shopping": AmapCategory("shopping", "购物", "060000"),
    "lodging": AmapCategory("lodging", "住宿", "100000"),
    "transport": AmapCategory("transport", "交通", "150000"),
    # 综合搜索：不限制 types，让关键字自己决定命中什么。仅供关键字搜索使用。
    "all": AmapCategory("all", "", ""),
}

# 高德 typecode 前缀 -> 客户端分类。长前缀优先匹配。
_TYPE_CODE_PREFIX_TO_CATEGORY: tuple[tuple[str, str], ...] = (
    ("0505", "drink"),
    ("0506", "drink"),
    ("0507", "drink"),
    ("0508", "drink"),
    ("05", "food"),
    ("06", "shopping"),
    ("10", "lodging"),
    ("11", "scenic"),
    ("14", "scenic"),
    ("15", "transport"),
)


def get_amap_category(category: str) -> AmapCategory | None:
    return AMAP_CATEGORY_MAPPING.get(category)


def infer_category(type_code: str | None, fallback: str = "scenic") -> str:
    """Map a raw AMap typecode onto a client-facing category.

    Comprehensive keyword search does not filter by type, so each result has to
    be tagged from its own typecode instead of from the requested category.
    """
    if not type_code:
        return fallback
    # 一个 POI 可能带多个 typecode，用 | 分隔，取第一个作为主分类。
    primary = type_code.split("|")[0].strip()
    for prefix, category in _TYPE_CODE_PREFIX_TO_CATEGORY:
        if primary.startswith(prefix):
            return category
    return fallback
