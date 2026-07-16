# 高德真实 POI 第一阶段

本阶段把探索页从本地模拟地点切换为“FastAPI 代理高德 Web 服务”的真实 POI 数据流。

## 数据流

```text
Android ExploreScreen
→ ExploreViewModel
→ ExploreRepository
→ Retrofit ApiService
→ FastAPI /api/explore/*
→ 高德 Web 服务 API
```

Android 只保存高德 Android 地图 SDK Key。高德 Web 服务 Key 只放在后端，不进入 Android。

## Key 配置

在 `backend/.env` 中配置：

```env
AMAP_WEB_SERVICE_KEY=你的高德Web服务Key
```

示例文件 `backend/.env.example` 只保留空占位：

```env
AMAP_WEB_SERVICE_KEY=
```

`.gitignore` 已忽略 `.env`，不要提交真实 Key。

## 后端接口

### 健康检查

```http
GET /api/health
GET /api/health/amap
```

`/api/health/amap` 只返回 Key 是否配置，不调用高德真实服务，不消耗配额。

### 地点输入提示

```http
GET /api/explore/input-tips
```

参数：

- `keyword`：搜索词，少于 2 个字符直接返回空列表
- `adcode`：当前城市行政区编码
- `category`：项目内部分类，可选
- `city_limit`：默认 `true`

返回 `PlaceSuggestion` 列表，不返回高德原始 JSON。

### POI 搜索

```http
GET /api/explore/pois/search
```

参数：

- `adcode`：必填
- `category`：`scenic / food / drink / shopping / lodging / transport`
- `keyword`：可选
- `page`：默认 1
- `page_size`：默认 20，最大 30
- `city_limit`：默认 `true`

返回统一分页模型：

```json
{
  "items": [],
  "page": 1,
  "pageSize": 20,
  "total": 0,
  "hasMore": false
}
```

## 分类映射

Android 只传项目分类，具体高德类型码和关键词由 FastAPI 管理：

- `scenic`：景点
- `food`：美食
- `drink`：饮品
- `shopping`：购物
- `lodging`：住宿
- `transport`：交通

## Android 行为

- 首次进入探索页，请求北京景点真实 POI。
- 切换城市后，地图先移动到城市中心，再请求该城市当前分类 POI。
- 切换分类后，请求当前城市对应分类 POI。
- 点击 Marker 或底部地点卡片，会同步选中地点并移动地图。
- 点击顶部搜索区域打开地点搜索层，输入至少两个字后请求高德输入提示。
- 接口失败时显示错误和重试，不用模拟数据冒充真实数据。

## 缓存与限制

后端使用轻量内存缓存，不引入 Redis：

- 输入提示缓存约 45 秒
- 分类 POI 缓存约 5 分钟
- 关键字搜索缓存约 3 分钟

限制：

- `page_size` 最大 30
- keyword 最大 60 字符
- 不无限分页
- 不缓存真实 Key
- 不长期缓存高德错误

## 当前未实现

- 地点详情真实化
- 天气
- Android 定位权限
- 地理编码和逆地理编码
- 路线规划和导航
- 加入旅行计划
- 收藏和打卡
- 小红书或其他内容平台
- AI 推荐理由

## 手动验证建议

1. 在 `backend/.env` 配置 `AMAP_WEB_SERVICE_KEY`。
2. 启动 FastAPI。
3. 打开 Swagger，测试 `/api/health/amap`。
4. 测试 `/api/explore/pois/search?adcode=110100&category=scenic`。
5. 测试 `/api/explore/input-tips?keyword=广州塔&adcode=440100`。
6. 在 Android Studio 运行 App。
7. 进入探索页，检查北京景点是否加载。
8. 切换广州市，检查地图和底部地点是否更新。
9. 切换美食、饮品、购物、住宿、交通。
10. 搜索“广州塔”，点击结果，检查地图是否定位到对应地点。
