# AI 旅行助手 MVP

本阶段把原来的 AI 占位页升级为“计划上下文问答”。

## 后端配置

在 `backend/.env` 中配置：

```env
ARK_API_KEY=你的火山方舟 API Key
ARK_MODEL=doubao-seed-2-1-pro-260628
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
```

后端不会把 Key 返回给 Android，也不会在健康检查中暴露 Key。

## 接口

- `GET /api/health/ai`：检查 AI 配置是否存在。
- `POST /api/ai/chat`：接收用户消息、最近历史和当前旅行计划上下文，返回真实 AI 回复。

AI 只做分析、建议和问答，不直接修改计划。

## 验证

```powershell
cd F:\travel-app\backend
.\.venv\Scripts\python.exe -m compileall app
.\.venv\Scripts\python.exe -m app.scripts.verify_ark
```

如果 Key、模型、额度或网络异常，脚本会输出安全错误，不输出真实 Key。
