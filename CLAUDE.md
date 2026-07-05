# TouchMemory — Claude Code 사용 규칙 (이 저장소 전용, 공방 헌법과 무관)

## ⚠️ 운영 환경 — 반드시 먼저 확인 (2026-07-05 갤럭시 전환 이후)
- TouchMemory의 실제 운영 서버(Source of Truth)는 이 맥북이 아니라 **갤럭시(Termux, Tailscale 사설망)**에 있다.
- **CLI를 실행하기 전에 반드시 이 저장소 루트의 `.env` 파일에서 `API_BASE_URL` 값을 먼저 읽어서 그 값으로 export하고 써라.**
  (`.env`는 Python이 직접 안 읽으므로 — `grep API_BASE_URL .env` 등으로 값을 확인한 뒤 `export API_BASE_URL=<그 값>`을 먼저 실행하고 CLI를 호출한다.)
  셸 환경변수도 없고 `.env`에도 값이 없거나 `127.0.0.1`로만 적혀 있을 때만 — **그때 비로소** 추측하지 말고 사용자에게 물어본다.
- **이 저장소에서 로컬 API 서버(`uvicorn`/`run.sh`)를 절대 새로 기동하지 않는다.** "서버가 안 떠 있다"는 이유로
  로컬에 서버를 띄우는 행동은 금지 — 맥북 로컬 DB와 갤럭시 DB가 갈라지는 사고로 직결된다(2026-07-05 실제 발생 사례).
- 포트 8787에 이미 뭔가 떠 있어도 그게 진짜 운영 서버라고 가정하지 않는다 — 좀비 로컬 프로세스일 수 있다.

- 이 프로젝트는 Anthropic Claude API를 호출하지 않는다. Claude Code는 아래 CLI 도구만 실행한다.
- 전제: TouchMemory API 서버가 떠 있어야 하며, `API_BASE_URL`(기본 `http://127.0.0.1:8787`)이 유효해야 한다.
- 자연어 → 실행 도구 매핑:
  - "오늘 건드릴 기억 보여줘"/"오늘 뭐 봐야 해" → `python -m touchmemory.cli list --today`
  - "이거 TouchMemory에 저장해: …" → `python -m touchmemory.cli add "…" [--project ..] [--remind ..] [--date ..] [--persistent]`
  - "N번 항목 수정해: …" → `python -m touchmemory.cli edit N [--content ..] [옵션]`
  - "이 기억(N번) 삭제해" → `python -m touchmemory.cli delete N`
  - "프로젝트 X 기억 보여줘" → `python -m touchmemory.cli list --project X`
