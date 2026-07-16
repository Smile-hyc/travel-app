package com.heoclub.aitravel.data.local

import com.heoclub.aitravel.data.model.ExploreCity
import com.heoclub.aitravel.data.model.ExploreProvince

object ExploreCityData {
    val provinces: List<ExploreProvince> = listOf(
        ExploreProvince("北京市", listOf(city("beijing", "北京市", "北京市", "110100", 39.9042, 116.4074, true))),
        ExploreProvince("天津市", listOf(city("tianjin", "天津市", "天津市", "120000", 39.0842, 117.2008, true))),
        ExploreProvince("上海市", listOf(city("shanghai", "上海市", "上海市", "310000", 31.2304, 121.4737, true))),
        ExploreProvince("重庆市", listOf(city("chongqing", "重庆市", "重庆市", "500000", 29.5630, 106.5516, true))),
        ExploreProvince(
            "河北省",
            listOf(
                city("shijiazhuang", "石家庄市", "河北省", "130100", 38.0428, 114.5149),
                city("qinhuangdao", "秦皇岛市", "河北省", "130300", 39.9354, 119.5996),
                city("chengde", "承德市", "河北省", "130800", 40.9515, 117.9634),
                city("zhangjiakou", "张家口市", "河北省", "130700", 40.8244, 114.8875),
            ),
        ),
        ExploreProvince(
            "山东省",
            listOf(
                city("jinan", "济南市", "山东省", "370100", 36.6512, 117.1201),
                city("qingdao", "青岛市", "山东省", "370200", 36.0671, 120.3826, true),
                city("yantai", "烟台市", "山东省", "370600", 37.4638, 121.4479),
                city("weihai", "威海市", "山东省", "371000", 37.5133, 122.1204),
            ),
        ),
        ExploreProvince(
            "江苏省",
            listOf(
                city("nanjing", "南京市", "江苏省", "320100", 32.0603, 118.7969, true),
                city("suzhou", "苏州市", "江苏省", "320500", 31.2989, 120.5853, true),
                city("wuxi", "无锡市", "江苏省", "320200", 31.4912, 120.3119),
                city("yangzhou", "扬州市", "江苏省", "321000", 32.3942, 119.4129),
            ),
        ),
        ExploreProvince(
            "浙江省",
            listOf(
                city("hangzhou", "杭州市", "浙江省", "330100", 30.2741, 120.1551, true),
                city("ningbo", "宁波市", "浙江省", "330200", 29.8683, 121.5440),
                city("wenzhou", "温州市", "浙江省", "330300", 27.9938, 120.6994),
                city("shaoxing", "绍兴市", "浙江省", "330600", 30.0303, 120.5802),
            ),
        ),
        ExploreProvince(
            "福建省",
            listOf(
                city("fuzhou", "福州市", "福建省", "350100", 26.0745, 119.2965),
                city("xiamen", "厦门市", "福建省", "350200", 24.4798, 118.0894, true),
                city("quanzhou", "泉州市", "福建省", "350500", 24.8741, 118.6759),
                city("zhangzhou", "漳州市", "福建省", "350600", 24.5135, 117.6471),
            ),
        ),
        ExploreProvince(
            "广东省",
            listOf(
                city("guangzhou", "广州市", "广东省", "440100", 23.1291, 113.2644, true),
                city("shenzhen", "深圳市", "广东省", "440300", 22.5431, 114.0579, true),
                city("zhuhai", "珠海市", "广东省", "440400", 22.2711, 113.5767),
                city("foshan", "佛山市", "广东省", "440600", 23.0215, 113.1214),
            ),
        ),
        ExploreProvince(
            "四川省",
            listOf(
                city("chengdu", "成都市", "四川省", "510100", 30.5723, 104.0665, true),
                city("leshan", "乐山市", "四川省", "511100", 29.5521, 103.7654),
                city("mianyang", "绵阳市", "四川省", "510700", 31.4675, 104.6796),
                city("dujiangyan", "都江堰市", "四川省", "510181", 30.9911, 103.6279),
            ),
        ),
        ExploreProvince(
            "陕西省",
            listOf(
                city("xian", "西安市", "陕西省", "610100", 34.3416, 108.9398, true),
                city("xianyang", "咸阳市", "陕西省", "610400", 34.3296, 108.7088),
                city("baoji", "宝鸡市", "陕西省", "610300", 34.3619, 107.2377),
                city("yanan", "延安市", "陕西省", "610600", 36.5853, 109.4898),
            ),
        ),
        ExploreProvince(
            "湖北省",
            listOf(
                city("wuhan", "武汉市", "湖北省", "420100", 30.5931, 114.3054, true),
                city("yichang", "宜昌市", "湖北省", "420500", 30.6919, 111.2865),
                city("xiangyang", "襄阳市", "湖北省", "420600", 32.0089, 112.1224),
                city("enshi", "恩施市", "湖北省", "422801", 30.2722, 109.4882),
            ),
        ),
        ExploreProvince(
            "湖南省",
            listOf(
                city("changsha", "长沙市", "湖南省", "430100", 28.2282, 112.9388, true),
                city("zhangjiajie", "张家界市", "湖南省", "430800", 29.1167, 110.4792),
                city("yueyang", "岳阳市", "湖南省", "430600", 29.3571, 113.1287),
                city("xiangtan", "湘潭市", "湖南省", "430300", 27.8298, 112.9441),
            ),
        ),
        ExploreProvince(
            "云南省",
            listOf(
                city("kunming", "昆明市", "云南省", "530100", 24.8801, 102.8329, true),
                city("dali", "大理市", "云南省", "532901", 25.6065, 100.2676, true),
                city("lijiang", "丽江市", "云南省", "530700", 26.8565, 100.2278),
                city("xishuangbanna", "西双版纳傣族自治州", "云南省", "532800", 22.0094, 100.7970),
            ),
        ),
        ExploreProvince(
            "海南省",
            listOf(
                city("haikou", "海口市", "海南省", "460100", 20.0444, 110.1983),
                city("sanya", "三亚市", "海南省", "460200", 18.2528, 109.5119, true),
                city("wanning", "万宁市", "海南省", "469006", 18.7951, 110.3897),
            ),
        ),
        ExploreProvince(
            "黑龙江省",
            listOf(
                city("harbin", "哈尔滨市", "黑龙江省", "230100", 45.8038, 126.5349, true),
                city("mudanjiang", "牡丹江市", "黑龙江省", "231000", 44.5517, 129.6332),
                city("yichun", "伊春市", "黑龙江省", "230700", 47.7281, 128.8405),
            ),
        ),
    )

    val allCities: List<ExploreCity> = provinces.flatMap { it.cities }
    val defaultCity: ExploreCity = allCities.first { it.id == "beijing" }
    val popularCities: List<ExploreCity> = allCities.filter { it.isPopular }

    fun searchCities(query: String): List<ExploreCity> {
        val normalized = query.trim()
        if (normalized.isBlank()) return emptyList()
        return allCities.filter { city ->
            city.name.contains(normalized, ignoreCase = true) ||
                city.displayName.contains(normalized, ignoreCase = true) ||
                city.provinceName.contains(normalized, ignoreCase = true) ||
                city.id.contains(normalized, ignoreCase = true)
        }
    }

    private fun city(
        id: String,
        name: String,
        provinceName: String,
        adCode: String,
        latitude: Double,
        longitude: Double,
        isPopular: Boolean = false,
        defaultZoom: Float = 13.2f,
    ): ExploreCity {
        return ExploreCity(
            id = id,
            name = name,
            displayName = name,
            provinceName = provinceName,
            adCode = adCode,
            latitude = latitude,
            longitude = longitude,
            defaultZoom = defaultZoom,
            isPopular = isPopular,
        )
    }
}
