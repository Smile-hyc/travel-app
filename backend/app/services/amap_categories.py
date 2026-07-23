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
}


def get_amap_category(category: str) -> AmapCategory | None:
    return AMAP_CATEGORY_MAPPING.get(category)
