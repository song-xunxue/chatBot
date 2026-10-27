#!/bin/bash
# V3.0 种子迁移(2026-08-17,幂等):从 V2.0 redis 复制「人设+功能配置」到 V3.0 独立 redis。
# 迁移:mychat:persona:*(人设卡+版本) mychat:mood:kinds|kind:*|params(档位配置)
#      mychat:plugin:*(插件开关参数) mychat:obj:*(对象-人设绑定)
# 不迁:chat:*(历史) mem:*(记忆) score:* mood:{oid}(心情值) takeover:* state:*(运行时,干净起步)
# 实现:类型感知搬运(string/set/hash/zset;值全文本 JSON,redis-cli DUMP|RESTORE 管道因转义不可用)。
# 用法:cd ~/ChatBot-V3 && sudo bash scripts/migrate_seed_from_v2.sh
set -e
SRC=mychat-redis-v2
DST=mychat-redis-v3

copy_key() {
  local k="$1" t v
  t=$(docker exec $SRC redis-cli TYPE "$k" | tr -d '\r\n')
  case "$t" in
    string)
      v=$(docker exec $SRC redis-cli GET "$k")
      docker exec $DST redis-cli SET "$k" "$v" >/dev/null ;;
    set)
      for m in $(docker exec $SRC redis-cli SMEMBERS "$k"); do
        docker exec $DST redis-cli SADD "$k" "$m" >/dev/null
      done ;;
    hash)
      for f in $(docker exec $SRC redis-cli HKEYS "$k"); do
        v=$(docker exec $SRC redis-cli HGET "$k" "$f")
        docker exec $DST redis-cli HSET "$k" "$f" "$v" >/dev/null
      done ;;
    zset)
      docker exec $SRC redis-cli ZRANGE "$k" 0 -1 WITHSCORES | paste - - | while IFS=$'\t' read -r m s; do
        docker exec $DST redis-cli ZADD "$k" "$s" "$m" >/dev/null
      done ;;
    *)
      echo "  跳过(未支持类型 $t): $k" ;;
  esac
}

echo "===== V3.0 种子迁移: $SRC → $DST ====="
total=0
for pattern in "mychat:persona:*" "mychat:mood:kinds" "mychat:mood:kind:*" "mychat:mood:params" "mychat:plugin:*" "mychat:obj:*"; do
  n=0
  for key in $(docker exec $SRC redis-cli --scan --pattern "$pattern"); do
    copy_key "$key"
    n=$((n+1))
  done
  echo "  $pattern → $n 条"
  total=$((total+n))
done
echo "===== 迁移完成,共 $total 条 ====="
echo "目标 DBSIZE: $(docker exec $DST redis-cli DBSIZE | tr -d '\r\n')"
echo "校验 persona:default 前 60 字节:"
docker exec $DST redis-cli GET mychat:persona:default | head -c 60; echo
