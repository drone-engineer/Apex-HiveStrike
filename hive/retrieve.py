"""검색 네 가지 — RAGAS로 비교한다.

  keyword : 기존 키워드 점수 검색 (문서 단위 → 각 문서의 첫 조각들)
  vector  : 질문 임베딩과 조각 임베딩의 코사인 유사도 상위 k
  hybrid  : keyword와 vector 순위를 RRF(역순위 합)로 섞는다 — 작은 임베딩 모델의 약점을 키워드가 보완
  graph   : hybrid 결과 문서에서 관계선을 1단계 따라가 이웃 문서의 가장 비슷한 조각을 더한다 (GraphRAG)

그래프 이웃은 NEO4J_URI가 있으면 Neo4j에서, 없으면 data/public/graph.json에서 읽는다.
"""
import json
import os
from functools import lru_cache

import numpy as np

from . import index, search
from .export import OUT

# 관계 종류별 가중치 — 호환·제조사가 추천 질문에 가장 쓸모 있다
REL_WEIGHT = {"COMPATIBLE_WITH": 1.0, "MANUFACTURED_BY": 0.8, "RELATED_TO": 0.7, "LINKS_TO": 0.5}
REL_KO = {"COMPATIBLE_WITH": "호환", "MANUFACTURED_BY": "제조사", "RELATED_TO": "관련 제품", "LINKS_TO": "본문 링크"}


def store():
    """색인 파일이 다시 만들어지면 자동으로 새로 읽는다."""
    return _store(index.vectors_file().stat().st_mtime)


@lru_cache(maxsize=1)
def _store(_mtime):
    chunks = json.loads((OUT / "chunks.json").read_text())
    vecs = np.load(index.vectors_file())
    docs = {d["path"]: d for d in json.loads((OUT / "docs.json").read_text())["docs"]}
    g = json.loads((OUT / "graph.json").read_text())
    by_doc = {}
    for c in chunks:
        by_doc.setdefault(c["path"], []).append(c["id"])
    nbr = {}
    for e in g["edges"]:
        if e["rel"] in REL_WEIGHT:  # IN_CATEGORY·CITES는 확장에 쓰지 않는다 (너무 넓거나 문서가 아님)
            nbr.setdefault(e["src"], []).append((e["dst"], e["rel"]))
            nbr.setdefault(e["dst"], []).append((e["src"], e["rel"]))
    return chunks, vecs, docs, by_doc, nbr


def neighbors(paths):
    """{문서: [(이웃, 관계)]} — Neo4j가 설정돼 있으면 거기서 읽는다."""
    if os.environ.get("NEO4J_URI"):
        from . import graphdb
        try:
            return graphdb.neighbors(paths, list(REL_WEIGHT))
        except Exception:  # Aura Free는 오래 안 쓰면 일시정지된다 — 그때는 같은 그래프를 파일에서 읽는다
            pass
    nbr = store()[4]
    return {p: nbr.get(p, []) for p in paths}


def _hit(c, score, via=None):
    return {"id": c["id"], "path": c["path"], "title": c["title"], "heading": c["heading"], "text": c["text"],
            "score": round(float(score), 4), "via": via}


def keyword(q, k=6):
    chunks, _, docs, by_doc, _ = store()
    ranked = search.search(list(docs.values()), q, limit=k)
    out = []
    for d in ranked:
        ids = by_doc.get(d["path"], [])
        # 문서 안에서는 검색어가 가장 많이 나오는 조각
        ts = search.terms(q)
        best = max(ids, key=lambda i: sum(chunks[i]["text"].lower().count(t) for t in ts), default=None)
        if best is not None:
            out.append(_hit(chunks[best], 0))
    return out[:k]


def vector(q, k=6, qv=None):
    chunks, vecs, *_ = store()
    qv = index.embed([q])[0] if qv is None else qv
    sims = vecs @ qv
    top = np.argsort(-sims)[: k * 3]
    out, seen = [], {}
    for i in top:  # 한 문서에서 조각 2개까지만 (다양성)
        p = chunks[i]["path"]
        if seen.get(p, 0) >= 2:
            continue
        seen[p] = seen.get(p, 0) + 1
        out.append(_hit(chunks[i], sims[i]))
        if len(out) == k:
            break
    return out


def hybrid(q, k=6, qv=None):
    """RRF: 각 목록에서 순위 r인 조각에 1/(60+r)점을 주고 더한다."""
    chunks = store()[0]
    score = {}
    for lst in (keyword(q, k * 2), vector(q, k * 2, qv)):
        for r, h in enumerate(lst):
            score[h["id"]] = score.get(h["id"], 0) + 1 / (60 + r)
    top = sorted(score, key=lambda i: -score[i])[:k]
    return [_hit(chunks[i], score[i]) for i in top]


def graph(q, k=6, expand=3):
    """hybrid 상위 k개 + 그래프 이웃 문서에서 질문과 가장 비슷한 조각 expand개."""
    chunks, vecs, docs, by_doc, _ = store()
    qv = index.embed([q])[0]
    base = hybrid(q, k, qv)
    have = {h["path"] for h in base}
    cand = {}
    for src, ns in neighbors(list(dict.fromkeys(h["path"] for h in base))).items():
        for dst, rel in ns:
            if dst in have or dst not in by_doc:
                continue
            ids = by_doc[dst]
            sims = vecs[ids] @ qv
            j = int(np.argmax(sims))
            s = float(sims[j]) * REL_WEIGHT[rel]
            if dst not in cand or s > cand[dst][0]:
                cand[dst] = (s, ids[j], f"{docs[src]['title']} —{REL_KO[rel]}→")
    extra = sorted(cand.values(), key=lambda x: -x[0])[:expand]
    return base + [_hit(chunks[i], s, via) for s, i, via in extra]


def graph_backend():
    return "Neo4j" if os.environ.get("NEO4J_URI") else "파일(graph.json)"


MODES = {"keyword": keyword, "vector": vector, "hybrid": hybrid, "graph": graph}
