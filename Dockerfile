# 多阶段构建:前端产物直接打进后端镜像,同域托管(PRD 第 7 节)
FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SNIPE_DB_PATH=/data/snipe.db \
    SNIPE_STATIC_DIR=/app/frontend/dist

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY --from=frontend /build/dist ./frontend/dist

VOLUME ["/data"]
EXPOSE 8000
# --proxy-headers + --forwarded-allow-ips:容器永远跑在反代后面(宝塔 Nginx 或
# 自带的 Caddy),不信任 X-Forwarded-For 的话 request.client.host 拿到的是反代的
# 地址,登录失败的 IP 限流会把全公司算成同一个来源。容器只监听内网/回环,
# 这里放开是安全的。
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000",      "--proxy-headers", "--forwarded-allow-ips", "*"]
