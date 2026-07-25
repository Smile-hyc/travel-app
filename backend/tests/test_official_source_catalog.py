from app.review_store import ReviewStore
from app.services.official_source_catalog import initialize_official_directory


def test_four_city_verified_sources_bind_to_top_poi_ids() -> None:
    store = ReviewStore(":memory:")
    initialize_official_directory(store)

    expected = {
        "B000A8UIN8": "https://www.dpm.org.cn/",
        "B000A45467": "https://www.badaling.cn/website/pc/index.html",
        "B000A7O1CU": "https://summerpalace.net.cn/",
        "B00157AW8O": "https://www.shanghaidisneyresort.com/zh-cn/",
        "B00150F6D6": "https://www.orientalpearltower.com/",
        "B00155MF55": "https://www.yugarden.com.cn/page/articleView/index.html",
        "B00154BDE9": "https://www.shjas.org/",
        "B000A840SB": "https://www.zhongshan-park.cn/",
        "B000A7I1OL": "https://www.bjjspark.cn/",
        "B001605O2L": "https://csgl.tj.gov.cn/ywzt/ylgl/sggyjj/202504/t20250427_6918928.html",
        "B00160CFPH": "https://towertj.net/",
        "B001609OZV": "https://www.mzhoudeng.com/html/",
        "B00170LAPL": "https://www.hongyanmuseum.cn/",
        "B0FFG8V7SH": "https://www.cq.gov.cn/zjcq/cycq/jplyxl/dsy/dsjp/202409/t20240905_13599455.html",
        "B0FFG2D40O": "https://www.cq.gov.cn/zjcq/cycq/jplyxl/dsy/dsjp/202409/t20240905_13599455.html",
        "B001702CBC": "https://chinabuddhism.com.cn/web/details/43515",
    }

    for poi_id, website_url in expected.items():
        source = store.get_official_source_by_poi(poi_id)
        assert source is not None
        assert source["discovery_status"] == "VERIFIED"
        assert source["website_url"] == website_url
        assert source["verified_at"]

    store.close()
