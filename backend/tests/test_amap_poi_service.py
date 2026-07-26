import asyncio

import pytest
from fastapi import HTTPException

from app.services.amap_poi_service import AmapPoiService


class FakeAmapClient:
    def __init__(self, districts):
        self._districts = districts

    async def get(self, path, params):
        assert path == "/v3/config/district"
        assert params["subdistrict"] == 1
        return {"districts": self._districts}


def test_province_search_returns_prefecture_cities() -> None:
    service = AmapPoiService(
        FakeAmapClient(
            [
                {
                    "name": "四川省",
                    "level": "province",
                    "adcode": "510000",
                    "center": "104.075931,30.651652",
                    "districts": [
                        {
                            "name": "成都市",
                            "level": "city",
                            "adcode": "510100",
                            "center": "104.066541,30.572269",
                        },
                        {
                            "name": "乐山市",
                            "level": "city",
                            "adcode": "511100",
                            "center": "103.765568,29.552106",
                        },
                    ],
                }
            ]
        )
    )

    cities = asyncio.run(service.search_cities(keyword="四川省", limit=12))

    assert [city.name for city in cities] == ["成都市", "乐山市"]
    assert all(city.provinceName == "四川省" for city in cities)


def test_direct_municipality_remains_one_destination() -> None:
    service = AmapPoiService(
        FakeAmapClient(
            [
                {
                    "name": "北京市",
                    "level": "province",
                    "adcode": "110000",
                    "center": "116.407387,39.904179",
                    "districts": [
                        {
                            "name": "东城区",
                            "level": "district",
                            "adcode": "110101",
                            "center": "116.416357,39.928353",
                        }
                    ],
                }
            ]
        )
    )

    cities = asyncio.run(service.search_cities(keyword="北京", limit=12))

    assert len(cities) == 1
    assert cities[0].name == "北京市"
    assert cities[0].adCode == "110000"


def test_direct_municipality_city_alias_is_canonicalized_and_deduplicated() -> None:
    service = AmapPoiService(
        FakeAmapClient(
            [
                {
                    "name": "北京城区",
                    "level": "city",
                    "adcode": "110100",
                    "center": "116.407387,39.904179",
                },
                {
                    "name": "北京市",
                    "level": "province",
                    "adcode": "110000",
                    "center": "116.407387,39.904179",
                    "districts": [],
                },
            ],
        ),
    )

    cities = asyncio.run(service.search_cities(keyword="北京市", limit=12))

    assert [(city.name, city.adCode, city.provinceName) for city in cities] == [
        ("北京市", "110000", "北京市"),
    ]


def test_prefecture_city_catalog_includes_municipalities_and_province_children() -> None:
    class CatalogClient:
        async def get(self, path, params):
            assert path == "/v3/config/district"
            assert params["subdistrict"] == 2
            return {
                "districts": [
                    {
                        "name": "中华人民共和国",
                        "level": "country",
                        "adcode": "100000",
                        "center": "116.4,39.9",
                        "districts": [
                            {
                                "name": "北京市",
                                "level": "province",
                                "adcode": "110000",
                                "center": "116.4,39.9",
                                "districts": [],
                            },
                            {
                                "name": "浙江省",
                                "level": "province",
                                "adcode": "330000",
                                "center": "120.1,30.2",
                                "districts": [
                                    {
                                        "name": "杭州市",
                                        "level": "city",
                                        "adcode": "330100",
                                        "center": "120.2,30.3",
                                    },
                                ],
                            },
                        ],
                    },
                ],
            }

    cities = asyncio.run(AmapPoiService(CatalogClient()).list_prefecture_cities())

    assert [(city.name, city.adCode) for city in cities] == [
        ("北京市", "110000"),
        ("杭州市", "330100"),
    ]


def test_city_search_derives_its_real_province_from_adcode() -> None:
    service = AmapPoiService(
        FakeAmapClient(
            [
                {
                    "name": "成都市",
                    "level": "city",
                    "adcode": "510100",
                    "center": "104.066541,30.572269",
                }
            ]
        )
    )

    cities = asyncio.run(service.search_cities(keyword="成都", limit=12))

    assert cities[0].provinceName == "四川省"


def test_input_tips_excludes_results_outside_selected_city() -> None:
    class TipsClient:
        async def get(self, path, params):
            assert path == "/v5/place/text"
            return {
                "count": "4",
                "pois": [
                    {"id": "metro", "name": "成都东客站地铁站", "adcode": "510107", "location": "104.14,30.63", "type": "交通设施服务;地铁站", "typecode": "150500"},
                    {"id": "airport", "name": "成都双流国际机场", "adcode": "510116", "location": "103.95,30.57", "type": "交通设施服务;机场相关", "typecode": "150100"},
                    {"id": "cd", "name": "成都东站", "adcode": "510107", "location": "104.14,30.63", "type": "交通设施服务;火车站", "typecode": "150200"},
                    {"id": "nj", "name": "南京南站", "adcode": "320114", "location": "118.80,31.97", "type": "交通设施服务;火车站", "typecode": "150200"},
                ],
            }

    service = AmapPoiService(TipsClient())
    tips = asyncio.run(
        service.input_tips(
            keyword="高铁站",
            adcode="510100",
            category="transport",
            city_limit=True,
            latitude=None,
            longitude=None,
        )
    )

    assert [tip.name for tip in tips] == ["成都东站", "成都双流国际机场"]


def test_default_transport_hubs_merge_railway_high_speed_and_airport_searches() -> None:
    class NanjingTransportClient:
        async def get(self, path, params):
            assert path == "/v5/place/text"
            keyword = params["keywords"]
            pois = {
                "火车站": [
                    {"id": "nj", "name": "南京站", "adcode": "320106", "location": "118.797,32.087", "type": "交通设施服务;火车站", "typecode": "150200"},
                ],
                "高铁站": [
                    {"id": "njs", "name": "南京南站", "adcode": "320114", "location": "118.804,31.968", "type": "交通设施服务;火车站", "typecode": "150200"},
                ],
                "机场": [
                    {"id": "lukou", "name": "南京禄口国际机场", "adcode": "320115", "location": "118.862,31.742", "type": "交通设施服务;机场相关", "typecode": "150100"},
                ],
            }[keyword]
            return {"count": str(len(pois)), "pois": pois}

    tips = asyncio.run(
        AmapPoiService(NanjingTransportClient()).input_tips(
            keyword="火车站|机场",
            adcode="320100",
            category="transport",
            city_limit=True,
            latitude=None,
            longitude=None,
        )
    )

    assert {tip.name for tip in tips} == {"南京站", "南京南站", "南京禄口国际机场"}


def test_reverse_geocode_prefers_nearest_poi_within_50_meters() -> None:
    class ReverseClient:
        async def get(self, path, params):
            assert path == "/v3/geocode/regeo"
            assert params["radius"] == 50
            assert params["extensions"] == "all"
            return {
                "regeocode": {
                    "formatted_address": "四川省成都市成华区邛崃山路333号",
                    "addressComponent": {
                        "province": "四川省",
                        "city": "成都市",
                        "district": "成华区",
                        "adcode": "510108",
                    },
                    "pois": [
                        {"id": "far", "name": "远处商场", "distance": "86.2"},
                        {"id": "near", "name": "成都东站", "distance": "12.4"},
                    ],
                }
            }

    point = asyncio.run(
        AmapPoiService(ReverseClient()).reverse_geocode(
            latitude=30.6289,
            longitude=104.1407,
            radius=50,
        )
    )

    assert point.name == "成都东站"
    assert point.formattedAddress == "四川省成都市成华区邛崃山路333号"
    assert point.adCode == "510108"
    assert point.cityName == "成都市"
    assert point.matchedPoiWithin50m is True
    assert point.distanceMeters == 12


def test_reverse_geocode_uses_detailed_address_when_no_poi_is_nearby() -> None:
    class ReverseClient:
        async def get(self, path, params):
            return {
                "regeocode": {
                    "formatted_address": "四川省成都市武侯区天府一街",
                    "addressComponent": {
                        "province": "四川省",
                        "city": "成都市",
                        "district": "武侯区",
                        "adcode": "510107",
                    },
                    "pois": [{"id": "far", "name": "远处地点", "distance": "120"}],
                }
            }

    point = asyncio.run(
        AmapPoiService(ReverseClient()).reverse_geocode(
            latitude=30.55,
            longitude=104.06,
        )
    )

    assert point.name == "四川省成都市武侯区天府一街"
    assert point.matchedPoiWithin50m is False

def test_museum_search_uses_indoor_culture_type_codes() -> None:
    class MuseumClient:
        async def get(self, path, params):
            assert path == "/v5/place/text"
            assert "140100" in params["types"]
            assert params["keywords"] == "上海博物馆"
            return {
                "count": "1",
                "pois": [
                    {
                        "id": "museum-1",
                        "name": "上海博物馆",
                        "type": "科教文化服务;博物馆;博物馆",
                        "typecode": "140100",
                        "location": "121.475,31.228",
                        "adcode": "310101",
                        "cityname": "上海市",
                    },
                ],
            }

    result = asyncio.run(
        AmapPoiService(MuseumClient()).search_pois(
            keyword="上海博物馆",
            adcode="310000",
            category="museum",
            page=1,
            page_size=8,
            city_limit=True,
        ),
    )

    assert result.items[0].name == "上海博物馆"
    assert result.items[0].category == "museum"

def test_nearby_search_forwards_local_food_keyword() -> None:
    class NearbyClient:
        async def get(self, path, params):
            assert path == "/v5/place/around"
            assert params["keywords"] == "本帮菜"
            return {"count": "0", "pois": []}

    result = asyncio.run(
        AmapPoiService(NearbyClient()).search_nearby_pois(
            latitude=31.23,
            longitude=121.47,
            adcode="310000",
            category="food",
            keyword="本帮菜",
        ),
    )

    assert result == []


def test_comprehensive_search_omits_types_and_infers_category() -> None:
    """选着「景点」搜火锅店时走综合搜索：不限制 types，分类由 typecode 反推。"""

    captured: dict = {}

    class ComprehensiveClient:
        async def get(self, path, params):
            captured["path"] = path
            captured["params"] = params
            return {
                "count": "2",
                "pois": [
                    {
                        "id": "food-1",
                        "name": "海底捞火锅",
                        "type": "餐饮服务;中餐厅;火锅店",
                        "typecode": "050117",
                        "location": "117.20,39.13",
                        "adcode": "120101",
                        "cityname": "天津市",
                    },
                    {
                        "id": "hotel-1",
                        "name": "海底捞旁边的酒店",
                        "type": "住宿服务;宾馆酒店;宾馆酒店",
                        "typecode": "100100",
                        "location": "117.21,39.14",
                        "adcode": "120101",
                        "cityname": "天津市",
                    },
                ],
            }

    result = asyncio.run(
        AmapPoiService(ComprehensiveClient()).search_pois(
            keyword="海底捞",
            adcode="120000",
            category="all",
            page=1,
            page_size=20,
            city_limit=True,
        ),
    )

    assert captured["path"] == "/v5/place/text"
    assert "types" not in captured["params"]
    assert [item.category for item in result.items] == ["food", "lodging"]
    assert [item.categoryCode for item in result.items] == ["food", "lodging"]


def test_comprehensive_search_requires_keyword() -> None:
    class UnusedClient:
        async def get(self, path, params):  # pragma: no cover - 不应该被调用
            raise AssertionError("综合搜索缺少关键字时不应该请求高德")

    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(
            AmapPoiService(UnusedClient()).search_pois(
                keyword="   ",
                adcode="120000",
                category="all",
                page=1,
                page_size=20,
                city_limit=True,
            ),
        )

    assert excinfo.value.status_code == 422
