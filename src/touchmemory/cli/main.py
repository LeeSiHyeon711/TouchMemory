"""Claude Code용 항목 관리 CLI (FEAT-05 범위).

모든 데이터 접근은 중앙 API를 `X-Channel: claude_code` 헤더로 경유한다
(로컬 SQLite 직접 접근 금지 — 설계서 8-4, FEAT-05 10절).
"""
import argparse
import os
import sys

import httpx


class APIConnectionError(Exception):
    """API 서버에 연결할 수 없을 때."""


class APIRequestError(Exception):
    """API가 4xx/5xx 응답을 반환했을 때."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _base_url() -> str:
    return os.environ.get("API_BASE_URL", "http://127.0.0.1:8787")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m touchmemory.cli",
        description="TouchMemory 기억 항목 조회·등록·수정·삭제 CLI (Claude Code 전용)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="항목 목록 조회")
    p_list.add_argument("--project", default=None, help="프로젝트 태그로 필터")
    p_list.add_argument(
        "--status", choices=["all", "todo", "done"], default="all", help="상태 필터"
    )
    p_list.add_argument(
        "--today", action="store_true", help="오늘 요약에 포함되는 항목만 조회"
    )

    p_add = sub.add_parser("add", help="항목 등록")
    p_add.add_argument("content", help="기억할 내용")
    p_add.add_argument("--project", default=None, help="프로젝트 태그")
    p_add.add_argument(
        "--remind", choices=["none", "once", "daily"], default="none", help="리마인드 유형"
    )
    p_add.add_argument("--date", default=None, help="--remind once일 때 YYYY-MM-DD")
    p_add.add_argument(
        "--persistent", action="store_true", help="완료 후에도 오늘 요약에 지속 노출"
    )

    p_edit = sub.add_parser("edit", help="항목 수정 (넘긴 옵션만 반영)")
    p_edit.add_argument("id", type=int, help="항목 id")
    p_edit.add_argument("--content", default=None, help="수정할 내용")
    p_edit.add_argument("--project", default=None, help="수정할 프로젝트 태그")
    p_edit.add_argument(
        "--remind", choices=["none", "once", "daily"], default=None, help="리마인드 유형"
    )
    p_edit.add_argument("--date", default=None, help="--remind once일 때 YYYY-MM-DD")
    p_edit.add_argument(
        "--persistent", choices=["on", "off"], default=None, help="지속 노출 여부"
    )

    p_delete = sub.add_parser("delete", help="항목 삭제")
    p_delete.add_argument("id", type=int, help="항목 id")

    return parser


class CliAPI:
    def __init__(self, base_url: str):
        self._client = httpx.Client(
            base_url=base_url, headers={"X-Channel": "claude_code"}, timeout=10
        )

    def close(self) -> None:
        self._client.close()

    def _request(self, method: str, url: str, **kwargs) -> dict:
        try:
            response = self._client.request(method, url, **kwargs)
        except httpx.RequestError as exc:
            raise APIConnectionError(str(exc)) from exc
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except Exception:
                detail = response.text
            raise APIRequestError(response.status_code, detail)
        return response.json()

    def list(
        self, project: str | None = None, status: str = "all", today: bool = False
    ) -> list[dict]:
        params: dict[str, str | bool] = {"status": status}
        if project is not None:
            params["project"] = project
        if today:
            params["today"] = True
        return self._request("GET", "/items", params=params)

    def add(self, **fields) -> dict:
        return self._request("POST", "/items", json=fields)

    def edit(self, item_id: int, **patch) -> dict:
        return self._request("PATCH", f"/items/{item_id}", json=patch)

    def delete(self, item_id: int) -> bool:
        result = self._request("DELETE", f"/items/{item_id}")
        return bool(result.get("deleted", False))

    # def complete(self, item_id: int) -> dict:
    #     """P1 확장 지점 — 완료 처리(--done)는 이번 MVP 범위 아님(구현 안 함)."""
    #     return self._request("PATCH", f"/items/{item_id}", json={"is_done": True})


def render_items(items: list[dict]) -> str:
    if not items:
        return "(항목 없음)"

    headers = ["ID", "내용", "프로젝트", "상태", "리마인드"]
    rows = []
    for item in items:
        content = (item.get("content") or "").replace("\n", " ")
        if len(content) > 30:
            content = content[:29] + "…"
        project = item.get("project_tag") or "-"
        status = "완료" if item.get("is_done") else "미완료"

        remind_type = item.get("remind_type", "none")
        if remind_type == "once":
            remind = f"once({item.get('remind_date') or '-'})"
        elif remind_type == "daily":
            remind = "daily"
        else:
            remind = "-"
        if item.get("persistent_reminder"):
            remind += "(지속)"

        rows.append([str(item.get("id")), content, project, status, remind])

    widths = [
        max(len(header), *(len(row[i]) for row in rows))
        for i, header in enumerate(headers)
    ]
    lines = ["  ".join(h.ljust(w) for h, w in zip(headers, widths))]
    lines.append("  ".join("-" * w for w in widths))
    for row in rows:
        lines.append("  ".join(c.ljust(w) for c, w in zip(row, widths)))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    api = CliAPI(_base_url())
    try:
        if args.command == "list":
            items = api.list(project=args.project, status=args.status, today=args.today)
            print(render_items(items))
            return 0

        if args.command == "add":
            item = api.add(
                content=args.content,
                project_tag=args.project,
                remind_type=args.remind,
                remind_date=args.date,
                persistent_reminder=args.persistent,
            )
            print(f"등록 완료: #{item['id']}")
            return 0

        if args.command == "edit":
            patch: dict[str, object] = {}
            if args.content is not None:
                patch["content"] = args.content
            if args.project is not None:
                patch["project_tag"] = args.project
            if args.remind is not None:
                patch["remind_type"] = args.remind
            if args.date is not None:
                patch["remind_date"] = args.date
            if args.persistent is not None:
                patch["persistent_reminder"] = args.persistent == "on"

            if not patch:
                print(
                    "수정할 옵션이 없습니다"
                    "(--content/--project/--remind/--date/--persistent 중 하나 이상 지정)",
                    file=sys.stderr,
                )
                return 1

            item = api.edit(args.id, **patch)
            print(f"수정 완료: #{item['id']}")
            return 0

        if args.command == "delete":
            deleted = api.delete(args.id)
            if not deleted:
                print("해당 항목 없음", file=sys.stderr)
                return 1
            print(f"삭제 완료: #{args.id}")
            return 0

        return 1
    except APIConnectionError:
        print(
            "데이터 서버에 연결할 수 없습니다(API_BASE_URL 확인, 기본 http://127.0.0.1:8787)",
            file=sys.stderr,
        )
        return 2
    except APIRequestError as exc:
        if exc.status_code == 404:
            print("해당 항목 없음", file=sys.stderr)
        else:
            print(str(exc.detail), file=sys.stderr)
        return 1
    finally:
        api.close()
