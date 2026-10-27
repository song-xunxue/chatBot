#!/bin/bash
# V3.0 一键部署(2026-08-16):构建镜像 + 起 mychat-server-v3(8091) + 健康检查。
# 前置:V3.0/.env 已配(ADAPTER=onebot/ONEBOT_WS_TOKEN/ONEBOT_SELF_ID/LLM keys/ACCESS_TOKEN/REDIS_URL);
#      server/dashboard/dist 已存在(前端与 V2.0 相同可直接复制)。共用 V2.0 redis(外部网络)。
# 用法:cd ~/ChatBot-V3 && sudo bash scripts/deploy_v3.sh
set -e
cd "$(dirname "$0")/.."

echo "===== 1.构建镜像 + 起 V3.0 栈(8091) ====="
docker compose up -d --build

echo "===== 2.健康检查(等 app 起来,最多 30s) ====="
ok=0
for i in $(seq 1 10); do
  sleep 3
  if curl -sf http://127.0.0.1:8091/health > /tmp/v3_health.json 2>/dev/null; then
    ok=1; break
  fi
done
if [ "$ok" = "1" ]; then
  echo "V3.0 health 通过(第 $i 次尝试)"
  cat /tmp/v3_health.json
else
  echo "健康检查失败,最近日志:"
  docker logs mychat-server-v3 --tail 30
  exit 1
fi

echo ""
echo "===== 部署完成,容器状态 ====="
docker ps --filter name=mychat-server-v3 --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""
echo "验证: NapCat 反向WS应自动重连 ws://127.0.0.1:8091/ws(30s 内);health 的 onebot_connected 变 true 即通"
