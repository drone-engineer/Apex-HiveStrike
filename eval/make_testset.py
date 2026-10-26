"""RAGAS 평가용 질문·정답 세트 만들기 → eval/testset.json

  python -m eval.make_testset            # 단일 문서 20 + 관계(두 문서) 10

- 단일 문서: 분야별로 고르게 뽑은 문서의 한 절에서 사실 질문 1개
- 관계 질문: 그래프에서 호환·제조사·관련 제품으로 이어진 두 문서를 함께 봐야 답할 수 있는 질문 1개 (GraphRAG가 유리한 유형)
정답(reference)은 그 절의 내용만으로 쓴다. 만든 뒤 사람이 훑어보고 이상한 문항은 지운다.
"""
import json
import pathlib
import random
import re

from langchain_core.messages import HumanMessage

from hive import llm
from hive.export import OUT

HERE = pathlib.Path(__file__).parent
random.seed(7)

PROMPT_ONE = """아래는 드론 엔지니어링 위키 문서의 한 부분입니다. 드론 엔지니어가 실제로 물어볼 만한 질문 1개와,
이 자료만으로 쓴 정답을 만드세요.
- 질문은 문서 제목을 그대로 베끼지 말고 자연스러운 한국어로. 답이 자료에 분명히 있어야 합니다.
- 정답은 1~3문장, 자료의 수치·이름을 그대로 씁니다.
JSON으로만: {{"question": "...", "reference": "..."}}

<문서 제목="{title}" 절="{heading}">
{text}
</문서>"""

PROMPT_TWO = """아래 두 문서는 관계({rel})로 이어져 있습니다. 두 문서를 **모두** 봐야 답할 수 있는 질문 1개와 정답을 만드세요.
예: 제품의 제조사가 만드는 다른 제품, 호환 부품의 사양, 관련 제품과의 차이.
- 정답은 1~3문장, 두 자료의 수치·이름을 그대로 씁니다.
JSON으로만: {{"question": "...", "reference": "..."}}

<문서A 제목="{t1}">
{x1}
</문서A>
<문서B 제목="{t2}">
{x2}
</문서B>"""


def ask(prompt):
    out = llm.chat(json_mode=True, max_tokens=400).invoke([HumanMessage(prompt)]).content
    m = re.search(r"\{.*\}", out, re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        return None
    return d if d.get("question") and d.get("reference") else None


def main(n_one=20, n_two=10):
    chunks = json.loads((OUT / "chunks.json").read_text())
    graph = json.loads((OUT / "graph.json").read_text())
    by_doc = {}
    for c in chunks:
        if len(c["text"]) > 200 and c["heading"] not in ("개요",) and "출처" not in c["heading"]:
            by_doc.setdefault(c["path"], []).append(c)
    # 분야(최상위 폴더)별로 돌아가며 문서를 고른다
    by_top = {}
    for p in by_doc:
        by_top.setdefault(p.split("/")[0], []).append(p)
    for v in by_top.values():
        random.shuffle(v)
    picks, tops = [], sorted(by_top)
    while len(picks) < n_one and any(by_top.values()):
        for t in tops:
            if by_top[t] and len(picks) < n_one:
                picks.append(by_top[t].pop())
    items = []
    for p in picks:
        c = random.choice(by_doc[p])
        r = ask(PROMPT_ONE.format(title=c["title"], heading=c["heading"], text=c["text"]))
        if r:
            items.append({"kind": "단일 문서", "docs": [p], **r})
            print(len(items), r["question"])
    pairs = [e for e in graph["edges"] if e["rel"] in ("COMPATIBLE_WITH", "MANUFACTURED_BY", "RELATED_TO")
             and e["src"] in by_doc and e["dst"] in by_doc]
    random.shuffle(pairs)
    seen = set()
    for e in pairs:
        if len([i for i in items if i["kind"] == "관계"]) >= n_two:
            break
        if e["src"] in seen:
            continue
        seen.add(e["src"])
        a, b = random.choice(by_doc[e["src"]]), random.choice(by_doc[e["dst"]])
        r = ask(PROMPT_TWO.format(rel=e["rel"], t1=a["title"], x1=a["text"], t2=b["title"], x2=b["text"]))
        if r:
            items.append({"kind": "관계", "rel": e["rel"], "docs": [e["src"], e["dst"]], **r})
            print(len(items), r["question"])
    (HERE / "testset.json").write_text(json.dumps(items, ensure_ascii=False, indent=1))
    print("저장:", len(items), "문항 →", HERE / "testset.json")


if __name__ == "__main__":
    main()
