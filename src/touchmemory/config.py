"""설정 로드 — os.environ만 읽는다 (.env 파일 파싱 없음, FEAT-01 범위).

`.env` 파일 자체의 로딩/파싱은 run.sh(FEAT-06)의 책임이다.
이 모듈은 이미 프로세스 환경에 올라온 os.environ 값만 읽는다.
"""
import os

from pydantic import BaseModel


class AppConfig(BaseModel):
    db_path: str = "data/touchmemory.db"
    tz: str = "Asia/Seoul"
    api_base_url: str = "http://127.0.0.1:8787"


def load_settings() -> AppConfig:
    return AppConfig(
        db_path=os.environ.get("DB_PATH", "data/touchmemory.db"),
        tz=os.environ.get("TZ", "Asia/Seoul"),
        api_base_url=os.environ.get("API_BASE_URL", "http://127.0.0.1:8787"),
    )
