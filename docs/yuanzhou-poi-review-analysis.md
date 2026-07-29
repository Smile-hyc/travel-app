# 圆周旅迹 POI 真实评价实现分析

分析对象：`圆周旅迹_5.3.1.apk`

- SHA-256：`00C8ABFEA41980CBC5733F2EDB58C63A2B9CAC1B0EB2DD3690B55C2417EFFBC5`
- Android 包名：`com.chaochaoshishi.slytherin`
- 分析方式：JADX 1.5.5 静态反编译，仅分析客户端可见代码和资源

## 结论

圆周旅迹的景点详情页没有在 Android 客户端直接调用小红书搜索接口。客户端向圆周旅迹自己的后端请求完整 POI 详情，后端把 AI 汇总评价、原始内容链接和来源平台一起返回。

客户端默认服务地址为 `https://www.pitravel.cn`，详情扩展信息接口为：

```text
POST /api/slytherin/v2/poi/detail/more_info
```

请求模型 `PoiDetailMoreRequest` 包含：

```text
latitude
longitude
inner_poi_id
timezone
outer_poi_id
collection_id
source
```

响应模型 `PoiDetailMore` 中与截图对应的字段为：

```text
ai_generate_intro       AI 生成的地点介绍
ai_generate_comments    AI 汇总后的正面/负面评价
poi_source_list         可追溯的原始内容标题、链接和平台
image_detail_list       图片列表
map_poi_detail_related_data_list  关联计划/内容
poi_intro               营业时间、地址等地点资料
feedback_h5_url         信息反馈入口
```

`ai_generate_comments` 的单项结构：

```text
tag
content
source_link
source_platform
review_type
source_note_title
```

其中 `review_type = 0` 显示在绿色正面卡片，`review_type = 1` 显示在红色负面卡片。

`poi_source_list` 的单项结构：

```text
source_id
source_title
source_platform
source_type
source_link
```

客户端平台编号映射为：

| 编号 | 平台 |
|---:|---|
| 1 | 小红书 |
| 2 | 大众点评 |
| 3 | 马蜂窝 |
| 4 | 携程 |
| 5 | 微信公众号 |
| 6 | Apple Map |
| 7 | 圆周旅迹 |

来源区域默认只显示去重后的平台图标；展开后显示去重后的原文标题卡片，点击卡片直接打开服务端返回的 `source_link`。

## 小红书相关 SDK 的含义

APK 中确实存在 `com.xingin.xhsreactnative`、`com.xingin.xhssharesdk`、`xhscomm`、`xhstheme` 等小红书组件，也能找到小红书 RN 资源域名。这只能证明应用复用了小红书的客户端基础组件、主题或分享能力，不能证明“真实评价”由客户端直接调用小红书官方 API 获取。

## 无法从 APK 确认的内容

APK 只暴露圆周旅迹自有聚合接口，没有暴露它的服务端如何抓取、采购或同步小红书笔记。因此静态反编译无法确认其上游是小红书内部服务、官方合作接口、第三方内容服务，还是自建采集服务。

不建议直接复用圆周旅迹的私有接口。当前项目采用自己的后端适配层，把可替换的数据提供方转换为统一的 `ReviewSource`，并在没有额度或没有可追溯来源时隐藏“真实评价”，避免把高德地点信息或模型推断伪装成用户评价。
