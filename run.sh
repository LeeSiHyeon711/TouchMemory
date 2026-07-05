#!/usr/bin/env bash
# TouchMemory 실행 스크립트 (FEAT-06) — API 서버 + Discord 봇 동시 기동/생명주기 관리
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

# 1) .env 로드/export (Python은 os.environ만 읽으므로 여기서 export가 단일 책임)
set -a
[ -f .env ] && . ./.env
set +a

mkdir -p logs data backup

API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8787}"
API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8787}"

# 2) API 서버 기동(백그라운드)
uvicorn touchmemory.api.server:app --host "$API_HOST" --port "$API_PORT" \
    >> logs/api.log 2>&1 &
API_PID=$!

cleanup() { kill "$API_PID" "$BOT_PID" 2>/dev/null || true; }

# 3) API 헬스 체크(타임아웃) — 실패 시 API kill 후 종료
ready=0
for _ in $(seq 1 30); do
    if curl -sf "$API_BASE_URL/docs" >/dev/null 2>&1; then
        ready=1
        break
    fi
    sleep 1
done
if [ "$ready" -ne 1 ]; then
    echo "API 서버가 30초 안에 응답하지 않았습니다. logs/api.log를 확인하세요." >&2
    kill "$API_PID" 2>/dev/null || true
    exit 1
fi

# 4) Discord 봇 기동(백그라운드)
python3 -m touchmemory.bot >> logs/bot.log 2>&1 &
BOT_PID=$!

# 5) 종료 처리 — Ctrl+C/TERM 시 두 프로세스 함께 정리
trap 'cleanup; exit 130' INT TERM

echo "TouchMemory 기동 완료 (API pid=$API_PID, 봇 pid=$BOT_PID)"
echo "로그: logs/api.log, logs/bot.log"

# 6) 하나라도 먼저 죽으면 나머지 정리 후 그 종료 코드로 exit(고아 방지)
#    ★ set -e 안전 보정(설계서 8-5): 죽은 프로세스의 종료 코드를 비정상 값 그대로
#      가로채면 set -e가 cleanup 호출 전에 셸을 즉시 종료시킬 수 있다.
#      → 먼저 '|| status=$?'로 종료 코드를 가로채 변수에 캡처하고(셸 조기 종료 방지),
#        그 다음 cleanup(나머지 kill) → 명시적 exit "$status" 순서를 보장한다.
#      이렇게 하면 API/봇 어느 쪽이 먼저 죽어도 반드시 나머지가 정리된 뒤 종료된다.
#    ★ 이식성 보정: `wait -n`(bash 4.3+ 전용)은 macOS 기본 bash(3.2)에 없으므로
#      대신 `kill -0`으로 두 PID를 폴링해 먼저 죽은 쪽을 찾은 뒤, 이미 종료된 그
#      프로세스에 대한 `wait $PID`(즉시 반환, 종료 코드 회수)로 동일한 효과를 낸다.
status=0
while kill -0 "$API_PID" 2>/dev/null && kill -0 "$BOT_PID" 2>/dev/null; do
    sleep 1
done
if ! kill -0 "$API_PID" 2>/dev/null; then
    wait "$API_PID" || status=$?
else
    wait "$BOT_PID" || status=$?
fi
cleanup
exit "$status"
