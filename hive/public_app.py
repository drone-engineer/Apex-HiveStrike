"""사용자 화면 (공개). data/public/docs.json만 읽는다 — 볼트에는 접근하지 않는다.

  PYTHONPATH=. .venv/bin/python -m uvicorn hive.public_app:app --host 127.0.0.1 --port 8000
"""
import html
import json
import pathlib
import re

import markdown
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import answer, retrieve, search
from .export import OUT

HERE = pathlib.Path(__file__).parent
TYPE_KO = {"product": "제품", "technology": "기술", "company": "회사", "program": "사업", "hub": "목차", "raw": "원문", "internal": "사내"}
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
tpl = Jinja2Templates(directory=HERE / "templates")
tpl.env.filters["regex_clean"] = lambda t: re.sub(r"\[\^\w+\]|^> ?(\[!\w+\])?", "", t, flags=re.M)
tpl.env.filters["tk"] = lambda t: TYPE_KO.get(t, t or "-")

EXAMPLES = ["6S 멀티콥터에 맞는 모터와 프롭 추천", "PX4와 ArduPilot 차이", "소형 드론 탐지용 레이더 비교", "국내 드론 안전성 인증 절차"]
_cache = {"mtime": None, "data": None}


def data():
    f = OUT / "docs.json"
    if not f.exists():
        raise HTTPException(503, "공개 자료가 아직 없습니다. 관리자 화면에서 내보내기를 실행하세요.")
    m = f.stat().st_mtime
    if _cache["mtime"] != m:
        raw = json.loads(f.read_text())
        docs = raw["docs"]
        hubs = {d["category"]: d for d in docs if d["type"] == "hub"}
        label = lambda c: re.sub(r"^\d+\s*", "", hubs[c]["title"]) if c in hubs else c.rsplit("/", 1)[-1]
        tops = sorted({d["category"].split("/")[0] for d in docs})
        _cache.update(mtime=m, data={
            "docs": docs, "by_path": {d["path"]: d for d in docs}, "exported_at": raw["exported_at"],
            "label": label, "tops": tops,
            "nav": [("/", "지식기반 답변")] + [(f"/c/{t}", label(t)) for t in tops] + [("/search", "검색")],
        })
    return _cache["data"]


def page(request, name, active, **ctx):
    d = data()
    return tpl.TemplateResponse(request, f"public/{name}", {"nav": d["nav"], "active": active, "admin": False,
                                                           "exported_at": d["exported_at"], "label": d["label"], **ctx})


def answer_html(text):
    # 모델 출력은 HTML을 이스케이프한 뒤 마크다운으로만 꾸민다
    text = re.sub(r"(?<=\S)\n(?=[ \t]*(?:[*-]|\d+\.)[ \t])", "\n\n", text)  # 목록 앞 빈 줄이 없으면 마크다운이 목록으로 못 읽는다
    out = markdown.markdown(html.escape(text, quote=False), extensions=["tables", "sane_lists"])
    return re.sub(r"\[(\d+)\]", r'<a class="ref" href="#src-\1">[\1]</a>', out)  # [n] → 근거 목록으로


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    d = data()
    cats = [{"key": t, "label": d["label"](t), "count": sum(1 for x in d["docs"] if x["category"].startswith(t) and x["type"] != "hub"),
             "hub": d["by_path"].get(f"{t}/_overview")} for t in d["tops"]]
    recent = sorted((x for x in d["docs"] if x["type"] != "hub"), key=lambda x: str(x["updated"]), reverse=True)[:8]
    return page(request, "home.html", "/", title="지식기반 답변", cats=cats, recent=recent, examples=EXAMPLES,
                ask_on=answer.enabled())


@app.post("/ask", response_class=HTMLResponse)
def ask_form(request: Request, q: str = Form(...)):
    q = q.strip()[:500]
    d = data()
    if not answer.enabled():
        return page(request, "answer.html", "/", title="지식기반 답변", q=q, result=None, hits=search.search(d["docs"], q, 10),
                    snippet=search.snippet, ask_on=False)
    why = answer.allow(request.headers.get("cf-connecting-ip") or request.client.host)
    result = {"answer": "", "sources": [], "trace": [], "error": why} if why else answer.ask(q)
    return page(request, "answer.html", "/", title="지식기반 답변", q=q, result=result, body=answer_html(result["answer"]),
                hits=[], snippet=search.snippet, ask_on=True)


@app.post("/api/ask")
async def ask_api(request: Request):
    q = str((await request.json()).get("question", "")).strip()[:500]
    if not q:
        raise HTTPException(400, "question이 비었습니다.")
    if not answer.enabled():
        raise HTTPException(503, "답변 기능이 아직 켜지지 않았습니다.")
    why = answer.allow(request.headers.get("cf-connecting-ip") or request.client.host)
    if why:
        raise HTTPException(429, why)
    r = answer.ask(q)
    return JSONResponse({"question": q, "answer": r["answer"], "error": r["error"], "model": r["model"], "trace": r["trace"],
                         "sources": [{"n": i, "title": s["title"], "heading": s["heading"], "url": f"/doc/{s['path']}", "via": s["via"]}
                                     for i, s in enumerate(r["sources"], 1)]})


MODE_LABEL = {"graph": "GraphRAG", "hybrid": "키워드+벡터", "vector": "벡터", "keyword": "키워드"}


@app.get("/search", response_class=HTMLResponse)
def search_page(request: Request, q: str = "", mode: str = "graph"):
    if mode not in retrieve.MODES:
        mode = "graph"
    hits = retrieve.MODES[mode](q.strip()[:300], k=8) if q.strip() else []
    return page(request, "search.html", "/search", title="검색", q=q, hits=hits, mode=mode, modes=MODE_LABEL,
                graph_backend=retrieve.graph_backend(),
                by_path=data()["by_path"])


@app.get("/c/{cat:path}", response_class=HTMLResponse)
def category(request: Request, cat: str):
    d = data()
    docs = [x for x in d["docs"] if x["category"] == cat or x["category"].startswith(cat + "/")]
    if not docs:
        raise HTTPException(404)
    hub = d["by_path"].get(f"{cat}/_overview")
    groups = {}
    for x in docs:
        if x["type"] != "hub":
            groups.setdefault(x["category"], []).append(x)
    groups = [(c, d["label"](c), sorted(v, key=lambda x: x["title"])) for c, v in sorted(groups.items())]
    top = cat.split("/")[0]
    return page(request, "category.html", f"/c/{top}", title=d["label"](cat), cat=cat, hub=hub, groups=groups,
                parent=top if top != cat else None)


@app.get("/doc/{path:path}", response_class=HTMLResponse)
def doc(request: Request, path: str):
    d = data()
    x = d["by_path"].get(path)
    if not x:
        raise HTTPException(404)
    if x["type"] == "hub":
        return category(request, x["category"])
    back = [y for y in d["docs"] if f'href="/doc/{path}"' in y["html"] and y["type"] != "hub" and y is not x][:12]
    specs = {k: v for k, v in (x["fm"].get("specs") or {}).items() if v not in (None, "", [], {})} if isinstance(x["fm"].get("specs"), dict) else {}
    return page(request, "doc.html", f"/c/{x['category'].split('/')[0]}", title=x["title"], d=x, specs=specs, back=back)


@app.get("/healthz")
def healthz():
    d = data()
    return {"ok": True, "docs": len(d["docs"]), "exported_at": d["exported_at"], "answer": answer.enabled(),
            "graph": retrieve.graph_backend()}
