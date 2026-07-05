# TouchMemory — Claude Code 사용 규칙 (이 저장소 전용, 공방 헌법과 무관)

- 이 프로젝트는 Anthropic Claude API를 호출하지 않는다. Claude Code는 아래 CLI 도구만 실행한다.
- 전제: TouchMemory API 서버가 떠 있어야 하며, `API_BASE_URL`(기본 `http://127.0.0.1:8787`)이 유효해야 한다.
- 자연어 → 실행 도구 매핑:
  - "오늘 건드릴 기억 보여줘"/"오늘 뭐 봐야 해" → `python -m touchmemory.cli list --today`
  - "이거 TouchMemory에 저장해: …" → `python -m touchmemory.cli add "…" [--project ..] [--remind ..] [--date ..] [--persistent]`
  - "N번 항목 수정해: …" → `python -m touchmemory.cli edit N [--content ..] [옵션]`
  - "이 기억(N번) 삭제해" → `python -m touchmemory.cli delete N`
  - "프로젝트 X 기억 보여줘" → `python -m touchmemory.cli list --project X`
