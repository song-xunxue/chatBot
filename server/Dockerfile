# MyChat 服务端 Docker 镜像
# 作者: 李文煜
# 日期: 2026-06-15
FROM python:3.11-slim

# 1.工作目录
WORKDIR /app

# 2.系统依赖（编译部分纯 Python 包可能需要 gcc）
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

# 3.先装依赖（利用 Docker 层缓存，依赖不变则跳过重装）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple

# 4.复制应用代码（server/app/ -> /app/app/）
COPY app/ ./app/

# 5.切换到代码目录，使 main.py 的同级导入（from core.config）生效
WORKDIR /app/app

EXPOSE 8000

# 6.启动 uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
