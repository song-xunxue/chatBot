# MyChat 服务端 Docker 镜像
# 作者: 李文煜
# 日期: 2026-06-15
#
# 2026-06-19
# 变更说明：
#   1. 验证 C 部署适配：build context 改为项目根（见 docker-compose.yml），
#      COPY 时保留 server/ 层级，使 ws.py 的 sys.path.parents[3] 在容器内
#      正确指向 /app（其下含 shared/），与本地运行路径推导一致
#   2. 新增 COPY shared/ —— 修复容器内 import shared.protocol 的 ImportError
FROM python:3.11-slim

# 1.工作目录
WORKDIR /app

# 2.系统依赖（编译部分纯 Python 包可能需要 gcc）
#   先把容器内 debian 源换为国内镜像（清华），否则容器内 apt 访问境外
#   deb.debian.org 会卡住（trixie 用 deb822 格式的 debian.sources）
RUN sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g; s|security.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

# 3.先装依赖（利用 Docker 层缓存，依赖不变则跳过重装）
#   build context 为项目根，故 requirements 路径为 server/requirements.txt
COPY server/requirements.txt ./server/
RUN pip install --no-cache-dir -r server/requirements.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple

# 4.复制共享协议与应用代码（保留 server/ 层级）
#   镜像布局：/app/shared/、/app/server/app/、/app/dashboard_dist(前端面板产物)
#   使 ws.py 的 parents[3]==/app 能找到 shared
COPY shared/ ./shared/
COPY server/app/ ./server/app/
# M8：打入 Vue 管理面板构建产物（由 FastAPI 在 / 托管，浏览器直开 http://host:8000/）
COPY dashboard/dist ./dashboard_dist

# 5.切换到应用目录，使同级导入（from core.config）生效
WORKDIR /app/server/app

EXPOSE 8000

# 6.启动 uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
