"""관리자 화면 — 이 맥에서 볼트를 직접 읽고, 승인·보류·제외는 볼트의 기존 스크립트로 처리한다.

  PYTHONPATH=. .venv/bin/python -m uvicorn hive.admin_app:app --host 127.0.0.1 --port 8100

접근:
- 이 맥에서 직접(127.0.0.1) 열면 바로 들어온다.
- Cloudflare Tunnel로 들어온 요청(Cf-Connecting-IP 헤더 있음)은 ADMIN_PASSWORD 기본 인증이 필수다.
  (그 앞단에 Cloudflare Access 이메일 로그인을 한 겹 더 둔다)
"""
import base64
import collections
import datetime
import json
import os
import pathlib
import re
import secrets
import subprocess
import sys
from urllib.parse import quote, urlparse

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import export, render, search, vault
from .vault import VAULT

HERE = pathlib.Path(__file__).parent
TYPE_KO = {"product": "제품", "technology": "기술", "company": "회사", "program": "사업", "hub": "목차", "raw": "원문", "internal": "사내"}
SCRIPTS = VAULT / ".claude/scripts"
LOGS = VAULT / ".claude/logs"
PUBLIC_URL = os.environ.get("HIVE_PUBLIC_URL", "http://127.0.0.1:8000")
JOBS = ["bids", "grants", "aplua", "fw", "cuas-daily", "sbc-daily", "nav-daily", "wiki-lint-weekly", "wiki-graph"]
NAV = [("/", "현황"), ("/inbox", "수집함"), ("/review", "위키 검토"), ("/jobs", "예약 작업"), ("/browse", "문서")]

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
tpl = Jinja2Templates(directory=HERE / "templates")
tpl.env.filters["tk"] = lambda t: TYPE_KO.get(t, t or "-")


@app.middleware("http")
async def guard(request: Request, call_next):
    remote = "cf-connecting-ip" in request.headers or request.client.host not in ("127.0.0.1", "::1")
    if remote:
        pw = os.environ.get("ADMIN_PASSWORD")
        if not pw:
            return Response("관리자 비밀번호(ADMIN_PASSWORD)가 설정되지 않아 외부 접속을 막았습니다.", 403)
        auth = request.headers.get("authorization", "")
        ok = False
        if auth.startswith("Basic "):
            try:
                _, _, given = base64.b64decode(auth[6:]).decode().partition(":")
                ok = secrets.compare_digest(given, pw)
            except Exception:
                ok = False
        if not ok:
            return Response("로그인이 필요합니다.", 401, {"WWW-Authenticate": 'Basic realm="Apex HiveStrike admin"'})
    if request.method == "POST":  # 다른 사이트에서 보낸 폼 차단
        origin = request.headers.get("origin") or request.headers.get("referer") or ""
        if origin and urlparse(origin).netloc != request.headers.get("host"):
            return Response("다른 주소에서 온 요청은 받지 않습니다.", 403)
    resp = await call_next(request)
    resp.headers["X-Robots-Tag"] = "noindex"
    return resp


def page(request, name, active, **ctx):
    return tpl.TemplateResponse(request, f"admin/{name}", {
        "nav": NAV, "active": active, "admin": True, "public_url": PUBLIC_URL, "root": "", "readonly": False,
        "view_url": lambda path: f"/view?path={quote(path)}",
        "flash": request.query_params.get("msg"), "flash_kind": request.query_params.get("kind"), **ctx})


def back(url, msg, kind=""):
    return RedirectResponse(f"{url}?msg={quote(msg)}&kind={kind}", 303)


def run(args):
    r = subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, cwd=VAULT, timeout=120)
    return r.returncode, (r.stdout + r.stderr).strip()


def log_line(kind, text):
    with open(VAULT / "log.md", "a") as f:
        f.write(f"- {datetime.date.today()} | {kind} | {text} (웹 관리자 화면)\n")


# ---------- 데이터 ----------

def inbox_items():
    items = []
    for f in sorted((VAULT / "raw/_inbox").glob("*.md")):
        fm, body = vault.parse(f.read_text(encoding="utf-8"))
        items.append({"file": f.name, "rel": f"raw/_inbox/{f.name}", "fm": fm,
                      "title": fm.get("title") or f.stem, "status": fm.get("intake_status") or "검토중",
                      "kind": fm.get("raw_kind") or "?", "summary": fm.get("summary_ko") or vault.summary_of(body)})
    return items


def job_status():
    out = []
    for j in JOBS:
        f = LOGS / f"cron-{j}.log"
        if not f.exists():
            out.append({"job": j, "state": "기록 없음", "kind": "", "at": "", "tail": ""}); continue
        lines = f.read_text(errors="replace").splitlines()
        starts = [i for i, l in enumerate(lines) if re.match(rf"=== .* {re.escape(j)} 시작", l)]
        last = lines[starts[-1]:] if starts else lines[-20:]
        end = next((l for l in reversed(last) if re.match(rf"=== .* {re.escape(j)} 종료", l)), None)
        at = (re.match(r"=== (\S+ \S+)", last[0]) or [None, ""])[1] if last else ""
        if end is None:
            state, kind = "실행 중 또는 중단", "warn"
        elif end.rstrip().endswith(" 0"):
            state, kind = "성공", "ok"
        else:
            state, kind = "실패 (" + end.rsplit(" ", 1)[-1] + ")", "bad"
        out.append({"job": j, "state": state, "kind": kind, "at": at, "tail": "\n".join(last[-25:])})
    return out


def export_info():
    f = export.OUT / "docs.json"
    if not f.exists():
        return {"at": None, "count": 0}
    d = json.loads(f.read_text())
    return {"at": d["exported_at"], "count": len(d["docs"])}


# ---------- 화면 ----------

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    docs = vault.load("wiki")
    inbox = inbox_items()
    jobs = job_status()
    types = collections.Counter(d["type"] or "기타" for d in docs if d["type"] != "hub")
    status = collections.Counter(d["review_status"] for d in docs if d["type"] != "hub")
    ib_status = collections.Counter(i["status"] for i in inbox)
    ib_kind = collections.Counter(i["kind"] for i in inbox if i["status"] == "검토중")
    ws = sum(1 for _ in (VAULT / "workspaces").rglob("*.md")) if (VAULT / "workspaces").exists() else 0
    return page(request, "dashboard.html", "/", title="현황", types=types, status=status, total=sum(types.values()),
                ib_status=ib_status, ib_kind=ib_kind, ib_total=len(inbox), jobs=jobs,
                failed=[j for j in jobs if j["kind"] in ("bad", "warn")], exp=export_info(), ws=ws,
                public_count=sum(1 for d in docs if vault.is_public(d)))


@app.get("/inbox", response_class=HTMLResponse)
def inbox(request: Request, status: str = "검토중", kind: str = ""):
    items = inbox_items()
    counts = collections.Counter(i["status"] for i in items)
    shown = [i for i in items if (not status or i["status"] == status) and (not kind or i["kind"] == kind)]
    return page(request, "inbox.html", "/inbox", title="수집함", items=shown, counts=counts, status=status, kind=kind,
                kinds=sorted({i["kind"] for i in items}))


@app.post("/inbox/decide")
def inbox_decide(file: str = Form(...), status: str = Form(...), reason: str = Form(""), ret: str = Form("/inbox")):
    if status not in ("승인", "보류", "제외") or "/" in file or not (VAULT / "raw/_inbox" / file).exists():
        raise HTTPException(400)
    fm, _ = vault.parse((VAULT / "raw/_inbox" / file).read_text(encoding="utf-8"))
    thread = str(fm.get("discord_thread") or "")
    if thread:  # 수집함 게시글과 같은 경로로 처리 (태그·이동·큐·log·스레드 답글). #검토-요청 메시지 정리는 하지 않는다
        args = [SCRIPTS / "inbox_decide.py", thread, status, "--no-cleanup"] + (["--reason", reason] if reason else [])
        rc, out = run(args)
    else:
        args = [SCRIPTS / "discord_post.py", f"raw/_inbox/{file}", "--set-status", status] + (["--reason", reason] if reason else [])
        rc, out = run(args)
        if rc == 0:
            log_line("intake", f"raw/_inbox/{file} ({status}{': ' + reason if reason else ''})")
    if rc:
        return back(ret, f"처리 실패: {out[-300:]}", "bad")
    return back(ret, f"{status} 처리: {fm.get('title') or file}")


@app.get("/review", response_class=HTMLResponse)
def review(request: Request, status: str = "검토중"):
    docs = [d for d in vault.load("wiki") if d["type"] != "hub"]
    counts = collections.Counter(d["review_status"] for d in docs)
    shown = [d for d in docs if d["review_status"] == status]
    shown.sort(key=lambda d: d["mtime"], reverse=True)
    return page(request, "review.html", "/review", title="위키 검토", docs=shown[:200], counts=counts, status=status)


@app.post("/review/decide")
def review_decide(path: str = Form(...), status: str = Form(...), reason: str = Form(""), ret: str = Form("/review")):
    f = (VAULT / f"{path}.md").resolve()
    if status not in ("승인", "반려", "검토중") or not path.startswith("wiki/") or VAULT / "wiki" not in f.parents or not f.exists():
        raise HTTPException(400)
    if status != "승인" and not reason.strip():
        return back(ret, "반려·재검토는 이유를 적어 주세요.", "bad")
    rc, out = run([SCRIPTS / "discord_post.py", f"{path}.md", "--set-status", status] + (["--reason", reason] if reason else []))
    if rc:
        return back(ret, f"처리 실패: {out[-300:]}", "bad")
    log_line("review", f"{path}.md → {status}{': ' + reason if reason else ''}")
    ok, msg = _export()
    return back(ret, f"{status} 처리: {path} · {msg}", "" if ok else "bad")


@app.get("/jobs", response_class=HTMLResponse)
def jobs(request: Request):
    return page(request, "jobs.html", "/jobs", title="예약 작업", jobs=job_status())


@app.get("/browse", response_class=HTMLResponse)
def browse(request: Request, q: str = "", scope: str = "wiki"):
    if scope not in ("wiki", "raw", "workspaces"):
        scope = "wiki"
    docs = vault.load(scope)
    hits = search.search(docs, q, 50) if q else sorted(docs, key=lambda d: d["mtime"], reverse=True)[:50]
    return page(request, "browse.html", "/browse", title="문서", q=q, scope=scope, hits=hits, snippet=search.snippet)


@app.get("/view", response_class=HTMLResponse)
def view(request: Request, path: str):
    f = (VAULT / f"{path}.md").resolve()
    if VAULT.resolve() not in f.parents or not f.exists() or any(p.startswith(".") for p in pathlib.Path(path).parts):
        raise HTTPException(404)
    fm, body = vault.parse(f.read_text(encoding="utf-8"))
    paths = [p.relative_to(VAULT).with_suffix("").as_posix() for p in VAULT.glob("[!.]*/**/*.md")]
    html = render.to_html(body, render.make_resolver(paths, lambda p: f"/view?path={quote(p)}"))
    return page(request, "view.html", "/browse", title=vault.title_of(fm, body, path), path=path, fm=fm, html=html,
                public=path.startswith("wiki/") and fm.get("review_status", "승인") not in vault.NOT_PUBLIC)


def _export():
    """공개 자료(data/public/docs.json)를 다시 만든다 → (성공 여부, 안내 문구)."""
    r = subprocess.run([sys.executable, "-m", "hive.export"], capture_output=True, text=True, cwd=HERE.parent, timeout=300)
    if r.returncode:
        return False, f"내보내기 실패: {(r.stdout + r.stderr)[-300:]}"
    return True, f"공개 자료 {json.loads(r.stdout.splitlines()[0])['exported']}건을 다시 내보냈습니다"


@app.post("/export")
def do_export(ret: str = Form("/")):
    ok, msg = _export()
    return back(ret, msg, "" if ok else "bad")
