# 服务器部署指南

## 环境要求

- Python 3.10+
- SQLite 3（系统自带）
- 服务器需开放端口：8000（或通过 Nginx 代理）

## 1. 上传代码

```bash
scp -r backend/ user@your-server:/opt/travel-app/
cd /opt/travel-app/backend
```

## 2. 创建虚拟环境并安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

## 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，关键配置如下：
```

### 必须修改的配置项

```ini
# 生成随机密钥（Linux 命令：openssl rand -hex 32）
JWT_SECRET=your-random-64-character-hex-string

# SQLite 数据库文件路径（相对 backend 目录）
USER_DATABASE_PATH=data/users.sqlite3

# Token 过期时间
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# 验证码有效期
CAPTCHA_TTL_SECONDS=300

# 其他必要配置...
DEEPSEEK_API_KEY=your-deepseek-key
AMAP_WEB_SERVICE_KEY=your-amap-key
```

## 4. 启动服务

### 开发模式（测试用）
```bash
cd /opt/travel-app/backend
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 生产模式（通过 systemd 守护）

创建 `/etc/systemd/system/travel-api.service`：
```ini
[Unit]
Description=AI Travel API
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/travel-app/backend
Environment="PATH=/opt/travel-app/backend/.venv/bin"
ExecStart=/opt/travel-app/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable travel-api
sudo systemctl start travel-api
```

## 5. Nginx 反向代理（推荐）

```nginx
server {
    listen 443 ssl;
    server_name api.your-domain.com;

    ssl_certificate /etc/ssl/certs/your-cert.pem;
    ssl_certificate_key /etc/ssl/private/your-key.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE 支持（AI 流式对话需要）
        proxy_buffering off;
        proxy_read_timeout 300s;
    }
}
```

## 6. 数据库备份

SQLite 是单文件数据库，备份很简单：

```bash
# 手动备份
cp /opt/travel-app/backend/data/users.sqlite3 /backup/users_$(date +%Y%m%d).sqlite3

# 定时备份（crontab，每天凌晨 2 点）
0 2 * * * cp /opt/travel-app/backend/data/users.sqlite3 /backup/users_$(date +\%Y\%m\%d).sqlite3
```

## 7. Android 端配置

在 `android/local.properties` 中配置：
```properties
API_BASE_URL=https://api.your-domain.com
```

确保服务器 CORS 已正确配置（`.env` 中的 `DEV_CORS_ORIGINS`），生产环境下需要将 Android 包名对应的域名加入白名单，或使用 `*`（不推荐）。

## 故障排查

```bash
# 查看服务状态
sudo systemctl status travel-api

# 查看日志
sudo journalctl -u travel-api -f

# 检查端口
ss -tlnp | grep 8000

# 测试 API
curl http://127.0.0.1:8000/api/auth/captcha
```
