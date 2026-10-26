"""검색 색인 만들기 — docs.json에서 ① 절 단위 조각 ② 다국어 임베딩 ③ 관계 그래프를 만든다.

  python -m hive.index

결과 (data/public/):
  chunks.json   조각 목록 [{id, path, title, heading, text}]
  vectors.npy         조각 임베딩 — 로컬 MiniLM (정규화된 float32, 조각 순서와 같음)
  vectors_gemini.npy  조각 임베딩 — Gemini API (GOOGLE_API_KEY가 있을 때)
  graph.json    {"nodes": [...], "edges": [{"src", "dst", "rel"}]}

임베딩 방식 HIVE_EMBED=local|gemini (비우면 local).
  local  : 이 맥·평가용. 모델을 메모리에 올려 약 0.8GB가 필요하다.
  gemini : 배포용(무료 서버 메모리 512MB). 질문 임베딩도 API로 만들어 모델을 올리지 않는다.
"""
import json
import os
import re

import numpy as np

from .export import OUT

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"  # 한국어 지원, 무료 로컬 실행
GEMINI_MODEL = "gemini-embedding-001"
GEMINI_DIM = 768
CHUNK_CHARS = 500
WIKILINK = re.compile(r"\[\[([^\]|#]+)")
DOCLINK = re.compile(r'href="/doc/([^"#]+)"')

_model = None


def embedder():
    """원본 모델(fastembed) — 색인 만들기·경량판 만들기에 쓴다."""
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        _model = TextEmbedding(MODEL)
    return _model


SLIM_DIR = OUT.parent / "model"
_slim = None


def slim():
    """경량판 모델(hive.slim_model로 만든 data/model/) — 메모리 약 0.2GB. 질문 임베딩에 쓴다."""
    global _slim
    if _slim is None:
        import onnxruntime as ort
        from tokenizers import Tokenizer
        so = ort.SessionOptions()
        so.intra_op_num_threads = 1
        so.enable_cpu_mem_arena = False
        sess = ort.InferenceSession(str(SLIM_DIR / "model.onnx"), so, providers=["CPUExecutionProvider"])
        tok = Tokenizer.from_file(str(SLIM_DIR / "tokenizer.json"))
        tok.enable_truncation(128)
        tok.enable_padding()
        _slim = (sess, tok, {i.name for i in sess.get_inputs()})
    return _slim


def _slim_embed(texts):
    sess, tok, names = slim()
    out = []
    for i in range(0, len(texts), 32):
        enc = tok.encode_batch(texts[i:i + 32])
        ids = np.array([e.ids for e in enc], dtype=np.int64)
        mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
        feed = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in names:
            feed["token_type_ids"] = np.zeros_like(ids)
        h = sess.run(None, feed)[0].astype(np.float32)
        out.append((h * mask[..., None]).sum(1) / mask.sum(1, keepdims=True))  # 평균 풀링 (fastembed와 같음)
    return np.concatenate(out)


def backend():
    return "gemini" if os.environ.get("HIVE_EMBED") == "gemini" else "local"


def vectors_file(b=None):
    return OUT / ("vectors_gemini.npy" if (b or backend()) == "gemini" else "vectors.npy")


def _gemini(texts, task):
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    out = []
    for i in range(0, len(texts), 100):  # 한 번에 100개까지
        r = client.models.embed_content(model=GEMINI_MODEL, contents=texts[i:i + 100],
                                        config=types.EmbedContentConfig(task_type=task, output_dimensionality=GEMINI_DIM))
        out += [e.values for e in r.embeddings]
    return out


def embed(texts, b=None, query=True):
    if (b or backend()) == "gemini":
        v = np.array(_gemini(list(texts), "RETRIEVAL_QUERY" if query else "RETRIEVAL_DOCUMENT"), dtype=np.float32)
    elif query and (SLIM_DIR / "model.onnx").exists():
        v = _slim_embed(list(texts))
    else:
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
    texts = [f'{c["title"]} — {c["heading"]}\n{c["text"]}' for c in chunks]
    vecs = embed(texts, "local", query=False)
    if os.environ.get("GOOGLE_API_KEY"):
        np.save(vectors_file("gemini"), embed(texts, "gemini", query=False))
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
