"""클라우드 관리자 화면(읽기 전용)용 스냅샷 — data/public/admin_snapshot.json.

현황 숫자, 수집함 목록(제목·요약·원문 URL), 검토중·반려 위키 목록, 예약 작업 결과(로그 본문 제외)만 담는다.
사내 자료(workspaces/)는 개수만 센다.
"""
import collections
import datetime
import json

from . import vault
from .export import OUT


def build():
    from .admin_app import inbox_items, job_status  # 관리자 화면과 같은 계산
    docs = [d for d in vault.load("wiki") if d["type"] != "hub"]
    inbox = inbox_items()
    ws = vault.VAULT / "workspaces"
    return {
        "taken_at": datetime.datetime.now().isoformat(timespec="minutes"),
        "types": collections.Counter(d["type"] or "기타" for d in docs),
        "status": collections.Counter(d["review_status"] for d in docs),
        "public_count": sum(1 for d in docs if vault.is_public(d)),
        "ws": sum(1 for _ in ws.rglob("*.md")) if ws.exists() else 0,
        "inbox": [{"file": i["file"], "title": i["title"], "status": i["status"], "kind": i["kind"], "summary": i["summary"],
                   "fm": {k: i["fm"].get(k) for k in ("url", "publisher", "published")}} for i in inbox],
        "review": [{k: d[k] for k in ("path", "title", "type", "summary", "mtime", "review_status")}
                   for d in docs if d["review_status"] in vault.NOT_PUBLIC],
        "jobs": [{k: j[k] for k in ("job", "state", "kind", "at")} | {"tail": ""} for j in job_status()],
    }


def write():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "admin_snapshot.json").write_text(json.dumps(build(), ensure_ascii=False, default=str))


if __name__ == "__main__":
    write()
    print("ok")
