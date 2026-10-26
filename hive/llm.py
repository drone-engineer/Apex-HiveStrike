"""LLM 고르기 — 자동 순서: GOOGLE_API_KEY → Gemini, ANTHROPIC_API_KEY → Claude, 없으면 이 맥의 Ollama 로컬 모델.

  HIVE_LLM=gemini|claude|ollama|none  (비우면 자동)
  HIVE_GEMINI_MODEL Gemini 모델 (기본 gemini-2.5-flash)
  HIVE_MODEL       Claude 모델 (기본 claude-opus-5-5)
  HIVE_OLLAMA_MODEL Ollama 모델 (기본 gemma4:26b — 이 맥에서 초당 약 57토큰)
"""
import os
import urllib.request

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")


def _ollama_up():
    try:
        urllib.request.urlopen(OLLAMA_URL + "/api/tags", timeout=1.5)
        return True
    except Exception:
        return False


def backend():
    want = os.environ.get("HIVE_LLM", "")
    if want in ("gemini", "claude", "ollama", "none"):
        return want
    if os.environ.get("GOOGLE_API_KEY"):
        return "gemini"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "claude"
    return "ollama" if _ollama_up() else "none"


def chat(json_mode=False, max_tokens=4000):
    """LangChain 채팅 모델. json_mode면 JSON만 내도록 한다(Ollama는 format=json, Claude는 프롬프트로)."""
    b = backend()
    if b == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=os.environ.get("HIVE_GEMINI_MODEL", "gemini-2.5-flash"), temperature=0,
                                      max_output_tokens=max_tokens * 4,  # 생각(thinking) 토큰 몫까지
                                      response_mime_type="application/json" if json_mode else None)
    if b == "claude":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=os.environ.get("HIVE_MODEL", "claude-opus-5-5"), max_tokens=max(max_tokens, 16000))
    if b == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(model=os.environ.get("HIVE_OLLAMA_MODEL", "gemma4:26b"), base_url=OLLAMA_URL, reasoning=False,
                          temperature=0, num_ctx=16384, num_predict=max_tokens, format="json" if json_mode else None)
    raise RuntimeError("사용할 LLM이 없습니다 (ANTHROPIC_API_KEY 또는 Ollama 필요)")


def label():
    b = backend()
    return {"gemini": os.environ.get("HIVE_GEMINI_MODEL", "gemini-2.5-flash"),
            "claude": os.environ.get("HIVE_MODEL", "claude-opus-5-5"),
            "ollama": "Ollama " + os.environ.get("HIVE_OLLAMA_MODEL", "gemma4:26b"), "none": "없음"}[b]
