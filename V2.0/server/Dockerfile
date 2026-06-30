# MyChat V2.0 服务端 Docker 镜像
# 作者: 李文煜
# 日期: 2026-07-01
#
# 说明: QQ 官方机器人后端(FastAPI + uvicorn + pynacl 验签 + httpx REST)
# build context = V2.0/ 项目根(docker-compose.yml 中 context: .)
# 镜像布局: /app/server/app/(应用) + /app/dashboard/dist(前端面板) + /app/server/data(运行时数据,compose 挂卷)
# 关键: config.py 的 PROJECT_ROOT = parents[3],/app/server/app/core/config.py 向上三级 == /app(项目根)
#       使 .env / dashboard/dist / server/data 的相对路径在容器内与本地一致
#
# 2026-07-01
# 变更说明：
#   1. M9 部署:基于 V1.0 Dockerfile 模板适配 V2.0(去 shared/,dashboard/dist 落 /app/dashboard/dist)
FROM python:3.11-slim

# 1.工作目录
WORKDIR /app

# 2.系统依赖(gcc 编译纯 Python 包可能需要)+ 清华 debian 源
#   trixie 用 deb822 格式的 debian.sources,直接 sed 换源(沿用 V1.0 验证过的做法)
RUN sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g; s|security.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

# 3.先装 Python 依赖(层缓存:依赖不变则跳过),清华 pypi 镜像
COPY server/requirements.txt ./server/
RUN pip install --no-cache-dir -r server/requirements.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple

# 4.复制应用代码(保留 server/app/ 层级,使同级导入 from core.config 生效)
COPY server/app/ ./server/app/

# 5.前端面板构建产物(main.py 静态托管 PROJECT_ROOT/dashboard/dist → /app/dashboard/dist)
COPY dashboard/dist ./dashboard/dist

# 6.运行时数据目录占位(compose 用 bind 挂载 ./server/data 覆盖;此处仅防空)
RUN mkdir -p /app/server/data/persona /app/server/data/star_plugins

# 7.切换到应用目录(同级导入生效),暴露端口,启动 uvicorn
WORKDIR /app/server/app
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
