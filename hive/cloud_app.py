"""클라우드 배포용 — 주소 하나에 사용자 화면(/)과 관리자 화면(/admin, 읽기 전용 스냅샷).

  uvicorn hive.cloud_app:app --host 0.0.0.0 --port 7860

볼트 없이 data/public/(docs.json, admin_snapshot.json)만 읽는다.
승인·반려 같은 처리는 볼트와 디스코드가 있는 맥의 관리자 화면(hive.admin_app)에서 한다.
"""
import base64
import collections
import json
import os
import secrets

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from .export import OUT
from .public_app import app, tpl

ROOT = "/admin"
NAV = [(f"{ROOT}/", "현황"), (f"{ROOT}/inbox", "수집함"), (f"{ROOT}/review", "위키 검토"), (f"{ROOT}/jobs", "예약 작업")]


@app.middleware("http")
async def admin_guard(request: Request, call_next):
    if request.url.path == ROOT or request.url.path.startswith(ROOT + "/"):
        pw = os.environ.get("ADMIN_PASSWORD")
        if not pw:
            return Response("관리자 비밀번호(ADMIN_PASSWORD)가 설정되지 않았습니다.", 503)
        auth, ok = request.headers.get("authorization", ""), False
        if auth.startswith("Basic "):
            try:
                ok = secrets.compare_digest(base64.b64decode(auth[6:]).decode().partition(":")[2], pw)
            except Exception:
                ok = False
        if not ok:
            return Response("로그인이 필요합니다.", 401, {"WWW-Authenticate": 'Basic realm="Apex HiveStrike admin"'})
        resp = await call_next(request)
        resp.headers["X-Robots-Tag"] = "noindex"
        return resp
    return await call_next(request)


def snap():
    f = OUT / "admin_snapshot.json"
    if not f.exists():
        raise HTTPException(503, "관리자 스냅샷이 없습니다.")
    return json.loads(f.read_text())


def page(request, name, active, s, **ctx):
    return tpl.TemplateResponse(request, f"admin/{name}", {
        "nav": NAV, "active": active, "admin": True, "readonly": True, "root": ROOT, "public_url": "/",
        "view_url": lambda path: "/doc/" + path.removeprefix("wiki/") if path.startswith("wiki/") else "#",
        "flash": f"읽기 전용 스냅샷 ({s['taken_at']} 기준). 승인·반려 처리는 볼트가 있는 맥의 관리자 화면에서 합니다.",
        **ctx})


@app.get(ROOT)
def admin_root():
    return RedirectResponse(f"{ROOT}/", 307)


@app.get(f"{ROOT}/", response_class=HTMLResponse)
def dashboard(request: Request):
    s = snap()
    types, status = collections.Counter(s["types"]), collections.Counter(s["status"])
    ib_status = collections.Counter(i["status"] for i in s["inbox"])
    ib_kind = collections.Counter(i["kind"] for i in s["inbox"] if i["status"] == "검토중")
    docs = json.loads((OUT / "docs.json").read_text())
    return page(request, "dashboard.html", f"{ROOT}/", s, title="현황", types=types, status=status, total=sum(types.values()),
                ib_status=ib_status, ib_kind=ib_kind, ib_total=len(s["inbox"]), jobs=s["jobs"],
                failed=[j for j in s["jobs"] if j["kind"] in ("bad", "warn")],
                exp={"at": docs["exported_at"], "count": len(docs["docs"])}, ws=s["ws"], public_count=s["public_count"])


@app.get(f"{ROOT}/inbox", response_class=HTMLResponse)
def inbox(request: Request, status: str = "검토중", kind: str = ""):
    s = snap()
    items = s["inbox"]
    shown = [i for i in items if (not status or i["status"] == status) and (not kind or i["kind"] == kind)]
    return page(request, "inbox.html", f"{ROOT}/inbox", s, title="수집함", items=shown, status=status, kind=kind,
                counts=collections.Counter(i["status"] for i in items), kinds=sorted({i["kind"] for i in items}))


@app.get(f"{ROOT}/review", response_class=HTMLResponse)
def review(request: Request, status: str = "검토중"):
    s = snap()
    counts = collections.Counter(s["status"])
    return page(request, "review.html", f"{ROOT}/review", s, title="위키 검토", status=status, counts=counts,
                docs=[d for d in s["review"] if d["review_status"] == status])


@app.get(f"{ROOT}/jobs", response_class=HTMLResponse)
def jobs(request: Request):
    s = snap()
    return page(request, "jobs.html", f"{ROOT}/jobs", s, title="예약 작업", jobs=s["jobs"])


@app.get(f"{ROOT}/browse")
def browse():
    return RedirectResponse("/search", 307)
