"""Apex HiveStrike 웹 — 프로젝트 폴더의 .env를 읽어 환경변수로 둔다(이미 있는 값은 덮지 않음)."""
import os
import pathlib

_env = pathlib.Path(__file__).resolve().parents[1] / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        _k, _sep, _v = _line.partition("=")
        if _sep and _k.strip() and not _k.lstrip().startswith("#") and _v.strip():
            os.environ.setdefault(_k.strip(), _v.split(" #")[0].strip().strip('"'))
