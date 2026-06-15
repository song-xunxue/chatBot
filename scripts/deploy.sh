#!/usr/bin/env bash
# MyChat 服务端部署脚本（Ubuntu 22.04）
# 作者: 李文煜
# 日期: 2026-06-15
# 用法: 在服务器项目根目录执行  bash scripts/deploy.sh
set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "===== 1.检查并安装 Docker ====="
if ! command -v docker &> /dev/null; then
  echo "Docker 未安装，正在安装 docker.io + compose 插件..."
  apt-get update
  apt-get install -y docker.io docker-compose-plugin
  systemctl enable --now docker
fi
docker --version
docker compose version 2>/dev/null || docker-compose --version

echo "===== 2.检查 .env ====="
if [ ! -f .env ]; then
  echo "错误：项目根缺少 .env，请先  cp .env.example .env  并填写真实凭据"
  exit 1
fi

echo "===== 3.放行防火墙端口（ufw） ====="
if command -v ufw &> /dev/null; then
  ufw allow 8000/tcp || true
fi

echo "===== 4.构建并后台启动 ====="
docker compose build
docker compose up -d

echo "===== 5.健康检查（等待启动） ====="
sleep 6
if curl -sf http://127.0.0.1:8000/health; then
  echo ""
  echo "健康检查通过"
else
  echo "健康检查失败，请查看日志：docker compose logs"
fi

echo ""
echo "===== 部署完成，容器状态 ====="
docker compose ps
