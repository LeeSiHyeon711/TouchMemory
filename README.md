# TouchMemory

Discord 봇 + Claude Code CLI로 "오늘 뭘 다시 봐야 하는지"를 알려주는 개인용 기억 관리 도구.
중앙 API 서버(SQLite) 하나를 Discord 봇과 Claude Code CLI가 함께 바라본다.

## ① 개요

- **저장 계층**: SQLite (`memory_items` / `usage_events` / `settings`)
- **중앙 API 서버**: FastAPI(`touchmemory.api.server`) — Discord 봇과 CLI가 모두 이 API만 경유(직접 DB 접근 없음)
- **Discord 봇**: 슬래시 커맨드 4종(`/기억등록` `/기억조회` `/기억완료` `/오늘요약`) + `/설정` + 매일 지정 시각 능동 알림
- **Claude Code CLI**: `python -m touchmemory.cli`로 자연어 대화 중 항목 조회/등록/수정/삭제(저장소 루트 `CLAUDE.md` 참고)

## ② 설치

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## ③ .env 설정

```bash
cp .env.example .env
```

`.env`를 열어 아래 값을 채운다(`.env`는 `.gitignore`로 커밋에서 제외됨).

| 키 | 설명 | 기본값 |
|---|---|---|
| `DB_PATH` | SQLite DB 파일 경로 | `data/touchmemory.db` |
| `TZ` | 타임존(요약 판정·시각 기준) | `Asia/Seoul` |
| `API_BASE_URL` | 봇·CLI가 호출할 API 주소 | `http://127.0.0.1:8787` |
| `API_HOST` / `API_PORT` | API 서버 바인딩 주소/포트 | `127.0.0.1` / `8787` |
| `DISCORD_TOKEN` | Discord 봇 토큰(필수, 없으면 봇 기동 실패) | (없음) |
| `GUILD_ID` | 슬래시 커맨드를 즉시 반영할 서버 id (없으면 전역 동기화, 반영 지연 가능) | (없음) |
| `NOTIFY_TIME` | 매일 능동 알림 기본 발송 시각 `HH:MM` (settings에 값 있으면 그쪽 우선) | `08:00` |
| `NOTIFY_CHANNEL_ID` | 능동 알림을 보낼 기본 채널 id (settings에 값 있으면 그쪽 우선) | (없음) |

## ④ 기동 (run.sh)

```bash
./run.sh
```

1. `.env`를 로드/export한다.
2. API 서버(uvicorn)를 백그라운드로 기동하고 `GET /docs`가 응답할 때까지 최대 30초 대기한다.
3. 응답이 없으면 API를 정리하고 오류 종료(봇은 뜨지 않음).
4. API가 정상이면 Discord 봇(`python -m touchmemory.bot`)을 백그라운드로 기동한다.
5. **생명주기 관리**: 두 프로세스 중 하나라도 먼저 종료되면 즉시 감지해 나머지 프로세스를 정리(cleanup)한 뒤, 먼저 죽은 프로세스의 종료 코드로 `run.sh`가 종료된다. 고아 프로세스가 남지 않는다.
6. `Ctrl+C`(또는 `TERM`)로 종료하면 trap이 두 프로세스를 함께 정리하고 `exit 130`으로 종료된다.

로그는 `logs/api.log`, `logs/bot.log`에 계속 쌓인다(`tail -f logs/bot.log`로 확인).

최초 기동 시 `data/`가 없으면 자동 생성되고, API 서버의 `lifespan`이 `init_db()`를 호출해 DB 파일과 3개 테이블(`memory_items`/`usage_events`/`settings`)이 자동으로 만들어진다. 별도 마이그레이션 명령이 필요 없다.

## ⑤ Discord 커맨드

| 커맨드 | 설명 |
|---|---|
| `/기억등록 내용 [프로젝트] [리마인드] [날짜] [지속]` | 새 기억 항목 등록. `리마인드`는 아래 참고 |
| `/기억조회 [프로젝트] [상태]` | 항목 조회(`상태`: 전체/미완료/완료) |
| `/기억완료 id` | 항목 완료 처리(지속 리마인드 항목은 완료해도 계속 노출) |
| `/오늘요약` | 오늘 다시 봐야 할 항목 요약(능동 알림과 동일 포맷) |
| `/설정 [알림시각] [알림채널]` | 인자 없이 호출하면 현재 값 조회, 지정하면 즉시 반영(스케줄 재적용) |

### 리마인드(`remind_type`) 의미 — 반드시 정확히 이해할 것

- **`daily`**: 완료 처리 전까지 **매일** 오늘 요약에 노출된다.
- **`once`**: 필드 이름은 "once"이지만 동작은 1회성이 아니다. **지정한 `--date`(`remind_date`)가 되는 날부터 활성화되어, 완료 처리하기 전까지 매일 오늘 요약에 계속 노출**된다("하루만 뜨고 사라지는 1회성"이 아님).
- **`none`**: 평소엔 오늘 요약에 노출되지 않는다. 단, **등록일이 어제 이전이고 아직 미완료 상태면 자동으로 오늘 요약에 포함**된다(깜빡 잊고 방치된 항목을 다시 띄워주는 안전망).
- **`persistent_reminder`(지속)**: 위 리마인드 유형과 무관하게, `true`면 **완료 처리된 뒤에도** 오늘 요약에 계속 노출된다.

## ⑥ Claude Code CLI

저장소를 Claude Code로 열면 루트 `CLAUDE.md`의 자연어→CLI 매핑에 따라 아래처럼 실행된다(API 서버가 떠 있어야 함).

```bash
python -m touchmemory.cli list [--project X] [--status all|todo|done] [--today]
python -m touchmemory.cli add "내용" [--project X] [--remind none|once|daily] [--date YYYY-MM-DD] [--persistent]
python -m touchmemory.cli edit N [--content ..] [--project ..] [--remind ..] [--date ..] [--persistent on|off]
python -m touchmemory.cli delete N
```

`API_BASE_URL` 환경변수가 없으면 `http://127.0.0.1:8787`로 폴백한다. CLI는 Anthropic Claude API를 호출하지 않으며, Claude Code가 이 CLI 명령을 실행하는 방식으로만 동작한다(자세한 매핑표는 저장소 루트 `CLAUDE.md` 참고).

## ⑦ 안전 백업/복원

운영 중(WAL 모드)에는 `data/touchmemory.db`를 `cp`로 단순 복사하면 **불완전한 스냅샷이 될 위험**이 있다. 반드시 SQLite 온라인 백업 API(`.backup`)를 사용한다.

```bash
# 백업 (프로세스를 멈추지 않고 실행 가능)
mkdir -p backup
sqlite3 data/touchmemory.db ".backup 'backup/touchmemory-$(date +%Y%m%d-%H%M).db'"

# 복원
./run.sh 를 종료(Ctrl+C)
cp backup/touchmemory-<타임스탬프>.db data/touchmemory.db
./run.sh 재기동
```

주기적으로(예: 매일 1회) crontab 등으로 백업 명령을 실행해두면 좋다(자동화 자체는 이번 MVP 범위 밖이며, 위 명령을 사람이 또는 사용자 환경의 스케줄러로 직접 실행한다).

## ⑧ 재시작

- 정상 종료: 실행 중인 터미널에서 `Ctrl+C` → 두 프로세스가 함께 정리됨 → `./run.sh`로 재기동.
- 설정(알림 시각/채널) 변경 후에는 Discord `/설정` 커맨드로 즉시 반영되며 재시작이 필요 없다.
- 코드/의존성을 바꾼 경우에만 프로세스를 재시작(`Ctrl+C` 후 `./run.sh`)한다.

## ⑨ 1주일 실사용 체크

최소 1주일간 실제로 써보면서 아래를 확인한다.

- 매일 `NOTIFY_TIME`에 능동 알림이 오는지, 봇을 껐다 켰을 때 그날치 알림이 자동으로 보정 발송되는지.
- `/기억등록` → `/기억조회` → CLI `list`로 같은 항목이 보이는지(중앙 API/DB 공유 확인).
- 사용 로그(`usage_events`)로 실제 사용 패턴 확인:

```bash
sqlite3 data/touchmemory.db "SELECT event_type, channel, COUNT(*) FROM usage_events GROUP BY event_type, channel;"
sqlite3 data/touchmemory.db "SELECT * FROM usage_events ORDER BY created_at DESC LIMIT 20;"
```

- 최소 1회 이상 `.backup`으로 온라인 백업 후 복원해서 데이터가 유지되는지 확인.
