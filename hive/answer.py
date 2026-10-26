"""지식 기반 답변 — LangGraph 흐름(hive.agent)을 웹에서 부른다. 승인된 위키만 근거로 쓴다.

LLM이 없으면(HIVE_LLM=none, 또는 API 키·Ollama 둘 다 없음) 꺼지고 검색 결과만 보여 준다.
요금 보호: IP당 시간당 ASK_PER_HOUR회, 서버 전체 하루 ASK_PER_DAY회.
"""
import collections
import datetime
import os
import time

from . import llm

PER_HOUR = int(os.environ.get("ASK_PER_HOUR", "20"))
PER_DAY = int(os.environ.get("ASK_PER_DAY", "300"))

_hits = collections.defaultdict(collections.deque)
_day = {"date": None, "count": 0}


def enabled():
    return llm.backend() != "none"


def allow(ip):
    """요청 수 제한. 허용이면 None, 아니면 이유 문자열."""
    now, today = time.time(), datetime.date.today()
    if _day["date"] != today:
        _day.update(date=today, count=0)
    if _day["count"] >= PER_DAY:
        return "오늘 답변 한도를 모두 썼습니다. 내일 다시 이용해 주세요."
    q = _hits[ip]
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= PER_HOUR:
        return "질문이 너무 많습니다. 잠시 후 다시 시도해 주세요."
    q.append(now)
    _day["count"] += 1
    return None


def ask(question, mode="graph"):
    """→ {"answer", "sources", "trace", "model", "error"}"""
    from . import agent
    t = time.time()
    try:
        r = agent.run(question, mode)
    except Exception as e:  # LLM 연결 실패 등 — 사용자에게는 짧게
        return {"answer": "", "sources": [], "trace": [], "model": llm.label(), "error": f"답변을 만들지 못했습니다 ({type(e).__name__})."}
    return {"answer": r.get("answer", ""), "sources": r.get("contexts", []), "trace": r.get("trace", []),
            "model": llm.label(), "sec": round(time.time() - t, 1), "error": None}
