#!/usr/bin/env bash
# MyChat 服务端部署脚本
# 作者: 李文煜
# 日期: 2026-06-15
# 用法: 在服务器项目根目录执行  sudo bash scripts/deploy.sh
#
# 2026-06-19
# 变更说明：
#   1. 验证 C 适配 Ubuntu 24.04：官方源无 docker-compose-plugin，改用 Docker 官方源
#      （阿里云镜像）安装 docker-ce + compose 插件
#   2. 新增 docker 镜像加速（腾讯云内网加速器），避免 build 拉 docker hub 镜像超时
set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "===== 1.安装 Docker（Docker 官方源，适配 Ubuntu 24.04） ====="
# 检查 compose 插件是否就绪（docker 命令 + compose 子命令都可用才算装好）
if ! docker compose version &> /dev/null; then
  echo "Docker/Compose 未就绪，通过 Docker 官方源（阿里云镜像）安装..."
  # 卸载可能冲突的旧版本（如上次失败的 docker.io 残留）
  apt-get remove -y docker.io docker-doc docker-compose podman-docker containerd runc 2>/dev/null || true
  # 安装必要依赖
  apt-get update
  apt-get install -y ca-certificates curl gnupg
  # 添加 Docker 官方 GPG key（阿里云镜像）
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://mirrors.aliyun.com/docker-ce/linux/ubuntu/gpg | gpg --dearmor --yes -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  # 添加 Docker apt 源（阿里云镜像），codename/arch 取自当前系统
  CODENAME="$(. /etc/os-release && echo "$VERSION_CODENAME")"
  ARCH="$(dpkg --print-architecture)"
  echo "deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.gpg] https://mirrors.aliyun.com/docker-ce/linux/ubuntu ${CODENAME} stable" > /etc/apt/sources.list.d/docker.list
  apt-get update
  # 安装 docker-ce + compose 插件
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
  # 配置 docker 镜像加速（腾讯云内网加速器，加速拉取 docker hub 镜像）
  mkdir -p /etc/docker
  cat > /etc/docker/daemon.json <<'EOF'
{
  "registry-mirrors": ["https://mirror.ccs.tencentyun.com"]
}
EOF
  systemctl restart docker
  echo "Docker 安装完成，已配置腾讯云镜像加速"
fi
docker --version
docker compose version

echo ""
echo "===== 2.检查 .env ====="
if [ ! -f .env ]; then
  echo "错误：项目根缺少 .env，请先  cp .env.example .env  并填写真实凭据"
  exit 1
fi

echo ""
echo "===== 3.放行防火墙端口（ufw；腾讯云实际由安全组放行） ====="
if command -v ufw &> /dev/null; then
  ufw allow 8000/tcp || true
fi

echo ""
echo "===== 4.构建并后台启动 ====="
docker compose build
docker compose up -d

echo ""
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
