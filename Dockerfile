# 多阶段构建:前端产物直接打进后端镜像,同域托管(PRD 第 7 节)
#
# 国内服务器直连 npm / PyPI 经常超时。传镜像源地址就切过去,不传保持官方源,
# 国外或本地构建不受影响。docker compose 会自动从 .env 里读这两个值:
#   PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
#   NPM_REGISTRY=https://registry.npmmirror.com

FROM node:22-alpine AS frontend
WORKDIR /build

ARG NPM_REGISTRY=""

COPY frontend/package.json frontend/package-lock.json* ./
RUN if [ -n "$NPM_REGISTRY" ]; then npm config set registry "$NPM_REGISTRY"; fi \
    && (npm ci --no-audit --no-fund || npm install --no-audit --no-fund)

COPY frontend/ ./
RUN npm run build


FROM python:3.12-slim
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SNIPE_DB_PATH=/data/snipe.db \
    SNIPE_STATIC_DIR=/app/frontend/dist

ARG PIP_INDEX_URL=""

COPY backend/requirements.txt ./
# 直连 PyPI 超时的表现很有迷惑性:pip 会报
#   Could not find a version that satisfies the requirement X (from versions: none)
# 看着像版本冲突,其实是索引请求根本没拿到数据。放宽 retries/timeout 只能缓解,
# 真正的解法是换镜像源。
RUN if [ -n "$PIP_INDEX_URL" ]; then pip config set global.index-url "$PIP_INDEX_URL"; fi \
    && pip install --no-cache-dir --retries 5 --timeout 60 -r requirements.txt

COPY backend/app ./app
# 迁移脚本必须一起进镜像:容器启动时会跑 alembic upgrade head
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./alembic.ini
COPY --from=frontend /build/dist ./frontend/dist

VOLUME ["/data"]
EXPOSE 8000
# --proxy-headers + --forwarded-allow-ips:容器永远跑在反代后面(宝塔 Nginx 或
# 自带的 Caddy),不信任 X-Forwarded-For 的话 request.client.host 拿到的是反代的
# 地址,登录失败的 IP 限流会把全公司算成同一个来源。容器只监听内网/回环,
# 这里放开是安全的。
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
