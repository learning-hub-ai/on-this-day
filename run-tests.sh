#!/usr/bin/env bash
# run-tests.sh — 跑全部测试
#
# 用法：  ./run-tests.sh
#
# 集成测试需要本地 HTTP 服务（api.js 用相对路径 fetch，Node 的 fetch
# 不接受相对 URL）。本脚本自动起停服务，端口 8750 以避开常用端口。

set -uo pipefail
cd "$(dirname "$0")"

PORT=8750
FAILED=0

note() { printf '\n\033[1m%s\033[0m\n' "$1"; }

# --- Node 定位 ---
# 优先用 PATH 里的；否则试 ~/.local/opt 下的便携版
if command -v node >/dev/null 2>&1; then
  NODE=node
elif NODE=$(echo "$HOME"/.local/opt/node-*/bin/node 2>/dev/null) && [ -x "$NODE" ]; then
  :
else
  echo "⚠ 未找到 node —— 跳过 JS 测试，只跑 Python 部分"
  NODE=""
fi

# --- Python 部分（无需服务）---
note "词表规则校验"
python3 scripts/check_glossary.py || FAILED=1

note "注音算法（Python 复刻）"
python3 scripts/glossary_algo_check.py >/dev/null && echo "  ✅ 14 条断言通过" || FAILED=1

# --- JS 部分 ---
if [ -n "$NODE" ]; then
  note "注音匹配（glossary.test.mjs）"
  "$NODE" js/glossary.test.mjs | tail -3 || FAILED=1

  note "端到端（integration.test.mjs）"
  python3 serve.py "$PORT" >/dev/null 2>&1 &
  SERVER_PID=$!
  # shellcheck disable=SC2064
  trap "kill $SERVER_PID 2>/dev/null" EXIT
  sleep 2
  "$NODE" js/integration.test.mjs | tail -3 || FAILED=1
  kill $SERVER_PID 2>/dev/null
  trap - EXIT
fi

note "结果"
if [ "$FAILED" -eq 0 ]; then
  echo "  ✅ 全部通过"
else
  echo "  ❌ 有测试失败"
fi
exit "$FAILED"
