"""간단한 키워드 검색 — 제목·이름·태그·본문에 가중치를 둔 점수."""
import re

TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣._+-]+")
# 한국어 질문에 자주 붙는 말 (검색어에서 뺀다)
STOP = {"추천", "추천해줘", "알려줘", "뭐야", "무엇", "어떤", "있어", "좋은", "비교", "해줘", "대해", "관련", "그리고", "또는", "위한", "용"}
JOSA = ("에서는", "으로는", "에서", "으로", "에게", "까지", "부터", "보다", "처럼", "하고", "이랑", "는", "은", "이", "가", "을", "를", "의", "에", "와", "과", "도", "로", "랑")


def terms(q):
    out = []
    for t in TOKEN_RE.findall(q.lower()):
        if re.search(r"[가-힣]$", t) and len(t) > 2:
            for j in JOSA:
                if t.endswith(j) and len(t) - len(j) >= 2:
                    t = t[: -len(j)]
                    break
        if t not in STOP and len(t) >= 2:
            out.append(t)
    return out


def score(doc, ts):
    title = doc["title"].lower()
    fm = doc.get("fm") or {}
    meta = " ".join(str(fm.get(k, "")) for k in ("name", "tags", "use_cases", "manufacturer", "category")).lower()
    text = doc.get("text", doc.get("body", "")).lower()
    s = 0.0
    for t in ts:
        s += 8 * (t in title) + 4 * (t in meta) + min(text.count(t), 10)
    if doc.get("type") == "hub":
        s *= 0.3  # 목차 문서는 뒤로
    return s


def search(docs, q, limit=20):
    ts = terms(q)
    if not ts:
        return []
    ranked = sorted(((score(d, ts), d) for d in docs), key=lambda x: -x[0])
    return [d for s, d in ranked if s > 0][:limit]


def snippet(doc, q, width=160):
    text = re.sub(r"\s+", " ", re.sub(r"[#>*|`\[\]^]", " ", doc.get("text", doc.get("body", ""))))
    for t in terms(q):
        i = text.lower().find(t)
        if i >= 0:
            a = max(0, i - width // 3)
            return ("…" if a else "") + text[a:a + width] + "…"
    return doc.get("summary", "")[:width]
