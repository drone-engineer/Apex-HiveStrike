"""RAGAS 평가 — 같은 질문 세트로 검색 방식 4가지 + LangGraph 전체 흐름을 비교한다.

  python -m eval.run_ragas answer     # 1단계: 방식별 답 만들기 → eval/results/<방식>.json (이미 있으면 건너뜀)
  python -m eval.run_ragas score      # 2단계: RAGAS 채점 → eval/results/<방식>.scores.json
  python -m eval.run_ragas report     # 3단계: eval/report.md 표

방식: keyword · vector · hybrid · graph (검색 1회 + 답변 1회) / agent (graph + LangGraph 근거 검사·재검색)
지표:
  - 문서 적중률(LLM 없음): 질문을 만든 원본 문서가 근거 자료에 들어 있는 비율 — 검색 자체의 성능
  - RAGAS: faithfulness(답이 근거에 충실한가), answer_relevancy(질문에 맞는 답인가),
           context_precision(가져온 근거가 정답에 쓸모 있는가), context_recall(정답에 필요한 근거를 다 가져왔는가)
"""
import datetime
import json
import math
import pathlib
import sys
import time

from langchain_core.embeddings import Embeddings
from langchain_core.messages import HumanMessage, SystemMessage

from hive import agent, index, llm, retrieve

HERE = pathlib.Path(__file__).parent
RES = HERE / "results"
CONFIGS = ["keyword", "vector", "hybrid", "graph", "agent"]
LABEL = {"keyword": "키워드", "vector": "벡터", "hybrid": "키워드+벡터", "graph": "GraphRAG", "agent": "GraphRAG + LangGraph 근거 검사"}
METRICS = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]


def testset():
    return json.loads((HERE / "testset.json").read_text())


def single_pass(question, mode):
    """검색 1회 + 답변 1회 (분류는 '사실'로 고정 — 검색 방식만 비교하기 위해)."""
    st = {"question": question, "qtype": "사실", "contexts": retrieve.MODES[mode](question, k=6), "trace": []}
    st.update(agent.generate(st))
    return st


def make_answers():
    RES.mkdir(exist_ok=True)
    for cfg in CONFIGS:
        out = RES / f"{cfg}.json"
        if out.exists():
            print("건너뜀(이미 있음):", out.name)
            continue
        rows = []
        for t in testset():
            s = time.time()
            st = agent.run(t["question"], "graph") if cfg == "agent" else single_pass(t["question"], cfg)
            ctx = st.get("contexts", [])
            rows.append({"id": t["id"], "kind": t["kind"], "question": t["question"], "reference": t["reference"],
                         "answer": st.get("answer", ""), "contexts": [f'{c["title"]} — {c["heading"]}\n{c["text"]}' for c in ctx],
                         "ctx_docs": [c["path"] for c in ctx], "gold_docs": t["docs"],
                         "rounds": st.get("rounds"), "sec": round(time.time() - s, 1)})
            print(cfg, t["id"], rows[-1]["sec"], "초")
        out.write_text(json.dumps({"llm": llm.label(), "made_at": datetime.datetime.now().isoformat(timespec="minutes"),
                                   "rows": rows}, ensure_ascii=False, indent=1))


class LocalEmbeddings(Embeddings):
    """RAGAS answer_relevancy용 — 검색과 같은 다국어 임베딩 모델."""

    def embed_documents(self, texts):
        return index.embed(texts).tolist()

    def embed_query(self, text):
        return index.embed([text])[0].tolist()


def score():
    from ragas import EvaluationDataset, RunConfig, evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import Faithfulness, LLMContextPrecisionWithReference, LLMContextRecall, ResponseRelevancy

    judge = LangchainLLMWrapper(llm.chat(max_tokens=2000))
    emb = LangchainEmbeddingsWrapper(LocalEmbeddings())
    metrics = [Faithfulness(), ResponseRelevancy(), LLMContextPrecisionWithReference(), LLMContextRecall()]
    for cfg in CONFIGS:
        src, out = RES / f"{cfg}.json", RES / f"{cfg}.scores.json"
        if not src.exists() or out.exists():
            continue
        rows = json.loads(src.read_text())["rows"]
        ds = EvaluationDataset.from_list([{"user_input": r["question"], "response": r["answer"], "retrieved_contexts": r["contexts"],
                                           "reference": r["reference"]} for r in rows])
        res = evaluate(ds, metrics=metrics, llm=judge, embeddings=emb, run_config=RunConfig(timeout=300, max_workers=2),
                       show_progress=True)
        df = res.to_pandas()
        per = []
        for r, (_, s) in zip(rows, df.iterrows()):
            per.append({"id": r["id"], **{m: _num(s.get(m, s.get(_alias(m)))) for m in METRICS}})
        out.write_text(json.dumps({"judge": llm.label(), "scored_at": datetime.datetime.now().isoformat(timespec="minutes"),
                                   "per_question": per}, ensure_ascii=False, indent=1))
        print(cfg, "채점 완료")


def _alias(m):
    return {"context_precision": "llm_context_precision_with_reference"}.get(m, m)


def _num(v):
    try:
        v = float(v)
        return None if math.isnan(v) else round(v, 4)
    except (TypeError, ValueError):
        return None


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return (sum(xs) / len(xs), len(xs)) if xs else (None, 0)


def report():
    lines, ts = [], testset()
    kinds = sorted({t["kind"] for t in ts})
    head = ["방식", "문서 적중률"] + [f"적중률({k})" for k in kinds] + METRICS + ["평균 시간(초)"]
    lines += ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    meta = {}
    for cfg in CONFIGS:
        src = RES / f"{cfg}.json"
        if not src.exists():
            continue
        a = json.loads(src.read_text())
        rows = a["rows"]
        hit = lambda r: any(g in r["ctx_docs"] for g in r["gold_docs"])
        cells = [LABEL[cfg], f"{sum(map(hit, rows)) / len(rows):.0%}"]
        for k in kinds:
            sub = [r for r in rows if r["kind"] == k]
            cells.append(f"{sum(map(hit, sub)) / len(sub):.0%}" if sub else "-")
        sc = RES / f"{cfg}.scores.json"
        per = json.loads(sc.read_text())["per_question"] if sc.exists() else []
        for m in METRICS:
            v, n = _mean([p[m] for p in per])
            cells.append(f"{v:.3f}" + (f" (n={n})" if n < len(rows) else "") if v is not None else "-")
        cells.append(f"{sum(r['sec'] for r in rows) / len(rows):.1f}")
        lines.append("| " + " | ".join(cells) + " |")
        meta[cfg] = (a["llm"], json.loads(sc.read_text())["judge"] if sc.exists() else "-")
    gen = {v[0] for v in meta.values()}
    judge = {v[1] for v in meta.values()}
    body = (f"# RAGAS 평가 결과\n\n- 작성: {datetime.date.today()}\n- 질문 세트: `eval/testset.json` {len(ts)}문항 "
            f"(단일 문서 {sum(t['kind'] == '단일 문서' for t in ts)}, 관계 {sum(t['kind'] == '관계' for t in ts)})\n"
            f"- 답변 LLM: {', '.join(gen)} / 채점 LLM: {', '.join(judge)}\n"
            f"- 임베딩: `{index.MODEL}`\n\n" + "\n".join(lines) + "\n")
    (HERE / "report.md").write_text(body)
    print(body)


if __name__ == "__main__":
    {"answer": make_answers, "score": score, "report": report}[sys.argv[1] if len(sys.argv) > 1 else "report"]()
