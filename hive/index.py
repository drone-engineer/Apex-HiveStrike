"""검색 색인 만들기 — docs.json에서 ① 절 단위 조각 ② 다국어 임베딩 ③ 관계 그래프를 만든다.

  python -m hive.index

결과 (data/public/):
  chunks.json   조각 목록 [{id, path, title, heading, text}]
  vectors.npy   조각 임베딩 (정규화된 float32, 조각 순서와 같음)
  graph.json    {"nodes": [...], "edges": [{"src", "dst", "rel"}]}
"""
import json
import re

import numpy as np

from .export import OUT

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"  # 한국어 지원, 0.22GB — 배포 서버에서도 돈다
CHUNK_CHARS = 500
WIKILINK = re.compile(r"\[\[([^\]|#]+)")
DOCLINK = re.compile(r'href="/doc/([^"#]+)"')

_model = None


def embedder():
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        _model = TextEmbedding(MODEL)
    return _model


def embed(texts):
    v = np.array(list(embedder().embed(texts)), dtype=np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def chunk_doc(d):
    """## 절마다 나누고, 긴 절은 문단 경계에서 CHUNK_CHARS 안팎으로 자른다. 각 조각 앞에 문서 제목·절 제목을 붙인다."""
    parts = re.split(r"^## +(.+)$", d["text"], flags=re.M)
    sections = [("개요", parts[0])] + list(zip(parts[1::2], parts[2::2]))
    out = []
    for heading, body in sections:
        body = re.sub(r"^\[\^\w+\]:.*$", "", body, flags=re.M)  # 각주 정의 줄은 빼고 본문만
        paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip() and not p.strip().startswith("# ")]
        buf = ""
        for p in paras:
            if buf and len(buf) + len(p) > CHUNK_CHARS:
                out.append((heading, buf)); buf = ""
            buf = f"{buf}\n\n{p}" if buf else p
        if buf:
            out.append((heading, buf))
    return [{"path": d["path"], "title": d["title"], "heading": h, "text": t} for h, t in out if len(t) > 30]


def links_in(value):
    return [m.strip().removesuffix(".md").removeprefix("wiki/") for m in WIKILINK.findall(json.dumps(value, ensure_ascii=False))]


def build_graph(docs):
    paths = {d["path"] for d in docs}
    stem = {p.rsplit("/", 1)[-1]: p for p in paths}
    norm = lambda t: t if t in paths else stem.get(t.rsplit("/", 1)[-1])
    nodes, edges = [], set()
    for d in docs:
        nodes.append({"id": d["path"], "title": d["title"], "type": d["type"], "category": d["category"]})
        fm = d["fm"]
        for t in links_in(fm.get("manufacturer")):
            if norm(t): edges.add((d["path"], norm(t), "MANUFACTURED_BY"))
        for t in links_in(fm.get("compatible_with")):
            if norm(t): edges.add((d["path"], norm(t), "COMPATIBLE_WITH"))
        for t in links_in(fm.get("related_products")):
            if norm(t): edges.add((d["path"], norm(t), "RELATED_TO"))
        for t in links_in(fm.get("products")):  # 회사 → 제품
            if norm(t): edges.add((norm(t), d["path"], "MANUFACTURED_BY"))
        hub = f'{d["category"]}/_overview'
        if d["type"] != "hub" and hub in paths:
            edges.add((d["path"], hub, "IN_CATEGORY"))
        for s in fm.get("sources") or []:
            if isinstance(s, dict) and s.get("url"):
                edges.add((d["path"], s["url"], "CITES"))
        for t in DOCLINK.findall(d["html"]):
            if t in paths and t != d["path"] and not t.endswith("_overview"):
                edges.add((d["path"], t, "LINKS_TO"))
    # 같은 쌍에 더 구체적인 관계가 있으면 LINKS_TO는 뺀다
    typed = {(a, b) for a, b, r in edges if r not in ("LINKS_TO", "CITES")}
    edges = [{"src": a, "dst": b, "rel": r} for a, b, r in sorted(edges) if not (r == "LINKS_TO" and (a, b) in typed)]
    return {"nodes": nodes, "edges": edges}


def main():
    docs = json.loads((OUT / "docs.json").read_text())["docs"]
    chunks = [c for d in docs if d["type"] != "hub" for c in chunk_doc(d)]
    for i, c in enumerate(chunks):
        c["id"] = i
    vecs = embed([f'{c["title"]} — {c["heading"]}\n{c["text"]}' for c in chunks])
    graph = build_graph(docs)
    (OUT / "chunks.json").write_text(json.dumps(chunks, ensure_ascii=False))
    np.save(OUT / "vectors.npy", vecs)
    (OUT / "graph.json").write_text(json.dumps(graph, ensure_ascii=False))
    rels = {}
    for e in graph["edges"]:
        rels[e["rel"]] = rels.get(e["rel"], 0) + 1
    print(json.dumps({"chunks": len(chunks), "dim": int(vecs.shape[1]), "nodes": len(graph["nodes"]), "edges": rels}, ensure_ascii=False))


if __name__ == "__main__":
    main()
