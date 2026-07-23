# 热门景点内容数据管道

## 当前实现

数据按高德 POI ID 统一，分为三层：

1. 高德事实层：名称、坐标、地址、营业时间、评分、电话与路线。
2. 景区官方层：预约、票价、临时闭园、节假日开放调整；保留官方 URL 和核验时间。
3. 授权 UGC / 自有评价层：只保存来源 ID/链接、匿名作者哈希、相关性、结构化标签、短摘要、证据 ID、更新时间和删除状态，不保存图片、视频与长原文。

热门 POI 目录有 25 个全国种子，也支持城市首次使用时通过高德自动发现 1～25 个热门景点。已发现地点写入采集目标；已知官方来源直接关联，尚未确认官网的地点进入 `PENDING` 官方目录，便于后续补齐而不是丢失。

城市自动建库默认采用 `12 / 30 / 20 / 8`：每座城市冻结 12 个热门景点，每个景点抓取 30 篇候选，清洗后最多保留 20 条有效证据，详情接口返回最相关的 8 条来源。高德第一页不直接等同于热度榜；系统先读取最多 50 个候选，排除入口、停车场、售票处等辅助 POI，再按评分、资料完整度和去重结果生成带版本号的榜单快照。

UGC 清洗包含：

- 正式 POI 名与常用简称匹配，并用城市/区县消歧；
- 删除 HTML、URL 和联系方式，限制摘要长度；
- 按来源笔记 ID 与规范化文本指纹去重；
- 过滤纯导流广告；
- 提取 `PHOTO`、`QUEUE`、`RESERVATION`、`WALKING`、`FOOD`、`WORTH_IT`；
- 1 个独立作者/证据即可形成低样本体验参考，界面必须展示样本量和免责声明；3 个及以上独立来源标记为交叉参考。

## 官方数据接入状态

已实现的官方网页连接器：故宫、九寨沟、黄山、秦始皇帝陵博物院、成都大熊猫繁育研究基地。黄山管委会页面如果返回 412，会降级使用黄山旅游官方交易平台的景区事实页，单站失败不会阻断其他景区同步。

故宫来源：

- 公告：[https://www.dpm.org.cn/announce.html](https://www.dpm.org.cn/announce.html)
- 预约、票价、开放规则：[https://www.dpm.org.cn/subject_booking/index.html](https://www.dpm.org.cn/subject_booking/index.html)
- 官方预约入口：[https://ticket.dpm.org.cn/](https://ticket.dpm.org.cn/)

连接器仅访问 HTTPS 域名白名单，手动校验重定向，限制 1 MB 响应和请求超时。它把官网当作可追溯文档源，不宣称存在官方开放 API，也不自动代订或抢票。

官方来源目录当前还记录八达岭、杭州西湖、上海迪士尼、陕西历史博物馆、南京博物院，包含官网、公众号、小程序或票务页面；尚未实现解析器的来源仍可在 App 展示官方入口。

已接入来源的抓取范围与限制：

| 景区 | 一手来源 | 建议抓取内容 | 注意事项 |
| --- | --- | --- | --- |
| 九寨沟 | `jiuzhai.com/news/notice`、`intelligent-service/tickets` | 公告、票价与预约规则 | 不抓库存，购票只跳官方渠道 |
| 黄山 | `hsgwh.huangshan.gov.cn/xwzx/tzgg/index.html`、`huangshan.com.cn` | 开放、索道/换乘、临时封闭、票价政策 | 管委会页面返回 412 时使用官方交易平台事实页降级 |
| 秦始皇帝陵博物院 | `bmy.com.cn/guide/` | 开放时间、承载量、实名预约、临时调整 | 授权票务承载页没有公开开发者 API |
| 成都大熊猫繁育研究基地 | `panda.org.cn/cn/service/ticket/` | 票价、预约、开放时间和承载量 | 只读公开页面，不处理订单或库存 |
| 八达岭长城 | `badaling.cn/website/pc/index.html` | 已进入官方来源目录，解析器待补 | 站内 JSON 无公开文档/SLA，保留 HTML 降级 |

这些景区当前未发现面向公众、承诺稳定性的票务/公告 OpenAPI。测试版可做限流、只读、可追溯的官网文档监测；商业版应与景区或票务承载方申请接口与内容使用授权。

## 运行方式

```powershell
cd F:\Projects\travel\backend
.\.venv\Scripts\python.exe scripts\sync_content.py --official-source dpm
.\.venv\Scripts\python.exe scripts\sync_content.py --official-source all
.\.venv\Scripts\python.exe scripts\sync_content.py --bootstrap-city 天津市 --limit 12
.\.venv\Scripts\python.exe scripts\sync_content.py --limit 10 --include-official
.\.venv\Scripts\python.exe scripts\sync_content.py --import-mediacrawler search_contents_2026-07-22.jsonl --city 天津市
```

自动城市管道：

```powershell
# 只生成并检查 Top 12 榜单
.\.venv\Scripts\python.exe scripts\build_city_content.py --city 杭州市 --plan-only

# 首次采集，浏览器需要时显示二维码
.\.venv\Scripts\python.exe scripts\build_city_content.py --city 杭州市

# 从 UTF-8 文件顺序处理多个城市
.\.venv\Scripts\python.exe scripts\build_city_content.py --cities-file cities.txt --headless

# 从高德行政区目录顺序处理全国城市。推荐可见浏览器模式，降低无头风控。
.\scripts\run_all_city_content.ps1

# 验证码中断或进程异常后，直接恢复已落盘 JSONL，不重复抓取
.\.venv\Scripts\python.exe scripts\build_city_content.py --recover-run <run-id>
```

每个城市只启动一个 MediaCrawler 进程，12 个 POI 作为同一批关键词顺序执行，评论、图片和视频采集保持关闭。每个运行目录保存 `manifest.json`、JSONL 和日志；清洗器通过清单中的精确查询词绑定高德 POI ID。命令中断后重新运行即可通过已有缓存跳过已完成 POI。

全国脚本遇到高德 `10021 / CUQPS` 时退避 15 秒后重试；只有日配额耗尽时才暂停到次日 00:05。小红书网络故障每 5 分钟重试；验证码出现前已经写入的 JSONL 会先清洗入库，随后暂停全国队列等待人工验证，不尝试绕过验证码。

城市任务状态为 `queued -> crawling -> cleaning -> ready`，失败时保留城市级错误及逐 POI 状态。原始运行目录保留 7 天，业务库长期保存的仍只有匿名化、结构化的短证据。

再次运行同一城市时先检查数据库缓存，只将无证据或已到期的 POI 交给采集器。榜单前 5 名刷新周期为 7 天，其余为 30 天；CLI 的 `--force` 用于明确要求全量重建。

任务会区分 `login_required`、`captcha_required`、`network_unavailable` 和真实空结果，不会把登录、验证或网络异常记作“该景点没有笔记”。处理完浏览器中的平台验证后重新运行全国脚本即可从缓存续跑。

HTTP 管理接口使用 `CONTENT_ADMIN_TOKEN`，并通过 `X-Content-Admin-Token` 请求头传入。令牌只能存放在后端。

## 生产化边界

- SQLite 与进程内任务适合单机测试；多实例前迁移到 PostgreSQL、Redis/Celery，并增加分布式 POI 锁。
- 官方页面保存 `source_url`、`published_at`、`verified_at`，后续增加 `content_hash`、`parser_version` 和解析失败告警。
- 临时闭园/节假日公告建议 5～15 分钟核验，规则与票价每日核验；支持 ETag/Last-Modified、指数退避与随机抖动。
- 只 GET 公开页面，遵守站点条款和 robots；不绕登录、验证码，不采集身份/订单，不轮询票务库存。
- UGC 商业上线必须有平台合作、内容采购或书面授权，并实现来源删除同步和审计。
