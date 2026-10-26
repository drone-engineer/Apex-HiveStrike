"""볼트(옵시디언) 문서 읽기 — 관리자 화면과 공개 내보내기가 같이 쓴다."""
import datetime
import os
import pathlib
import re

import yaml

VAULT = pathlib.Path(os.environ.get("HIVE_VAULT", pathlib.Path.home() / "cursor/claude_code_test"))
FM_RE = re.compile(r"^---\n(.*?)\n---\n?", re.S)

# 공개 사용자 화면에 내보내지 않는 상태 (CLAUDE.md 승인 게이트: 승인 문서만 서비스 근거)
NOT_PUBLIC = {"검토중", "반려"}


def _plain(v):
    """yaml 값 → JSON에 넣을 수 있는 값 (날짜는 문자열)."""
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()
    if isinstance(v, dict):
        return {str(k): _plain(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_plain(x) for x in v]
    return v


def parse(text):
    """(frontmatter dict, 본문) — yaml이 깨진 문서는 한 줄짜리 키만 정규식으로 읽는다."""
    m = FM_RE.match(text)
    if not m:
        return {}, text
    try:
        fm = yaml.safe_load(m.group(1)) or {}
        if not isinstance(fm, dict):
            raise ValueError
    except Exception:
        fm = {k: v.strip().strip('"') for k, v in re.findall(r"^(\w+):[ \t]*(.*)$", m.group(1), re.M)}
    return _plain(fm), text[m.end():]


def title_of(fm, body, path):
    h = re.search(r"^# (.+)$", body, re.M)
    return (h and h.group(1).strip()) or fm.get("name") or fm.get("title") or path.rsplit("/", 1)[-1]


def summary_of(body):
    for p in body.split("\n\n"):
        p = p.strip()
        if p and not p.startswith(("#", ">", "|", "-", "[^", "<", "```", "←")):
            return re.sub(r"\[\[(?:[^]|]*\|)?([^]]+)\]\]|\[\^\w+\]", r"\1", p)[:220]
    return ""


def load(folder="wiki"):
    """folder 아래 모든 .md → 문서 dict 목록. path는 볼트 기준 확장자 없는 경로."""
    docs = []
    for f in sorted((VAULT / folder).rglob("*.md")):
        rel = f.relative_to(VAULT).with_suffix("").as_posix()
        fm, body = parse(f.read_text(encoding="utf-8"))
        docs.append({
            "path": rel,
            "fm": fm,
            "body": body,
            "title": title_of(fm, body, rel),
            "summary": summary_of(body),
            "type": fm.get("type") or "",
            "review_status": fm.get("review_status") or "승인",  # 2026-10-11 이전 문서는 승인으로 본다
            "mtime": datetime.datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="minutes"),
        })
    return docs


def is_public(doc):
    return doc["path"].startswith("wiki/") and doc["review_status"] not in NOT_PUBLIC
