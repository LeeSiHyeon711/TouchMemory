"""봇 → 중앙 API httpx 클라이언트 래퍼 (FEAT-03 범위).

모든 요청에 `X-Channel: discord` 헤더를 고정해 채널별 사용 이벤트가
올바르게 집계되도록 한다(설계서 6절). 연결 실패/HTTP 오류는 커스텀
예외로 변환해 `bot/client.py`가 discord 응답 메시지로 옮기기 쉽게 한다.
"""
import httpx


class APIConnectionError(Exception):
    """API 서버에 연결할 수 없을 때."""


class APIRequestError(Exception):
    """API가 4xx/5xx 응답을 반환했을 때."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class TouchMemoryAPI:
    def __init__(self, base_url: str):
        self._client = httpx.AsyncClient(
            base_url=base_url, headers={"X-Channel": "discord"}, timeout=10
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, url: str, **kwargs) -> dict:
        try:
            response = await self._client.request(method, url, **kwargs)
        except httpx.RequestError as exc:
            raise APIConnectionError(str(exc)) from exc
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except Exception:
                detail = response.text
            raise APIRequestError(response.status_code, detail)
        return response.json()

    async def create_item(self, **fields) -> dict:
        return await self._request("POST", "/items", json=fields)

    async def list_items(
        self, project: str | None = None, status: str = "all", today: bool = False
    ) -> list[dict]:
        params: dict[str, str | bool] = {"status": status}
        if project is not None:
            params["project"] = project
        if today:
            params["today"] = True
        return await self._request("GET", "/items", params=params)

    async def complete_item(self, item_id: int) -> dict:
        return await self._request(
            "PATCH", f"/items/{item_id}", json={"is_done": True}
        )

    async def get_today_digest(self) -> dict:
        return await self._request("GET", "/digest/today")
