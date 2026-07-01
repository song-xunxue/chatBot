#!/usr/bin/env bash
# MyChat V2.0 服务端部署脚本(QQ 官方机器人后端)
# 作者: 李文煜
# 日期: 2026-07-01
# 用法: 在服务器 V2.0 项目根目录执行  sudo bash scripts/deploy_v2.sh
#
# 职责: docker compose 构建+启动 → 健康检查 → 把 nginx-ssl 加入 V2.0 网络 →
#       切换 nginx.conf(443 反代到 V2.0 app)→ reload nginx
# 前提: Docker 29+ 已装(沿用 V1.0 部署);nginx-ssl 容器在跑(443 HTTPS 终结);
#       项目根有 .env(真实 QQ 凭证 + LLM key)
# 2026-07-01
# 变更说明：
#   1. M9 部署:V2.0 一键部署脚本(独立栈 + 复用 nginx-ssl HTTPS)
set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "===== 0.前置检查 ====="
if [ ! -f .env ]; then
  echo "错误:项目根缺少 .env(真实 QQ 凭证)。请先放置 .env"
  exit 1
fi
if [ ! -d dashboard/dist ]; then
  echo "错误:缺少 dashboard/dist(前端构建产物)。本地先 cd dashboard && npm run build,再打包上传"
  exit 1
fi
docker --version
docker compose version

echo ""
echo "===== 1.构建并后台启动 V2.0(app + redis) ====="
docker compose build
docker compose up -d

echo ""
echo "===== 2.健康检查(等 app 起来,最多 30s) ====="
ok=0
for i in $(seq 1 15); do
  if curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; then
    echo "V2.0 health 通过(第 ${i} 次尝试)"
    curl -s http://127.0.0.1:8000/health
    echo ""
    ok=1
    break
  fi
  sleep 2
done
if [ "$ok" = "0" ]; then
  echo "健康检查失败,查看日志:docker compose logs server"
  docker compose logs --tail=40 server || true
  exit 1
fi

echo ""
echo "===== 3.nginx-ssl 加入 V2 网络(幂等) ====="
# 网络名由 compose 按项目名(目录名小写)前缀:如 ChatBot-V2/ → chatbot-v2_chatbot_v2_net
# 故从 server 容器实测其所在网络名,避免硬编码踩坑
V2_NET=$(docker inspect mychat-server-v2 --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}{{end}}' 2>/dev/null)
if [ -n "$V2_NET" ]; then
  echo "V2 网络名:$V2_NET"
  if ! docker network inspect "$V2_NET" --format '{{range $k,$v := .Containers}}{{println $v.Name}}{{end}}' | grep -q '^nginx-ssl$'; then
    docker network connect "$V2_NET" nginx-ssl
    echo "nginx-ssl 已加入 $V2_NET"
  else
    echo "nginx-ssl 已在网络中,跳过"
  fi
else
  echo "警告:未取到 V2 网络(mychat-server-v2 是否启动成功?)"
fi

echo ""
echo "===== 4.切换 nginx.conf(443 反代 → V2.0 app) ====="
NGINX_CONF_HOST=/opt/nginx-docker/conf/nginx.conf
if [ -f deploy/nginx.conf ]; then
  cp "$NGINX_CONF_HOST" "$NGINX_CONF_HOST.bak.$(date +%Y%m%d%H%M%S 2>/dev/null || echo bak)" 2>/dev/null || true
  cp deploy/nginx.conf "$NGINX_CONF_HOST"
  docker exec nginx-ssl nginx -t
  docker exec nginx-ssl nginx -s reload
  echo "nginx.conf 已切换并 reload(原配置备份为 .bak.*)"
else
  echo "跳过:无 deploy/nginx.conf(请手动配置 443 反代)"
fi

echo ""
echo "===== 部署完成,容器状态 ====="
docker compose ps
echo ""
echo "公网验证:"
echo "  curl https://www.songqingxun.icu/health"
echo "  curl -X POST https://www.songqingxun.icu/qq/webhook -H 'Content-Type: application/json' -d '{\"op\":13,\"d\":{\"plain_token\":\"test\",\"event_ts\":\"1725442341\"}}'"
