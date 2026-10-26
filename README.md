# Apex HiveStrike — 드론 엔지니어링 지식 서비스

Obsidian 지식 베이스와 GraphRAG로 드론 엔지니어의 자료 조사 업무를 자동화하는 AI 서비스.
자동 수집 → 사람 승인 → 한국어 위키 → GraphRAG 검색 → LangGraph 근거 검사 답변.

- 설계: [`docs/PRD.md`](docs/PRD.md)
- 평가: [`eval/report.md`](eval/report.md) (RAGAS)

## 구성

| 경로 | 내용 |
|---|---|
| `hive/vault.py`, `hive/export.py` | 옵시디언 볼트 읽기, 승인된 위키만 `data/public/`으로 내보내기 |
| `hive/index.py` | 절 단위 조각, 다국어 임베딩, 관계 그래프 |
| `hive/graphdb.py` | Neo4j 적재·이웃 질의 |
| `hive/retrieve.py` | 검색 4가지: 키워드 / 벡터 / 키워드+벡터 / GraphRAG |
| `hive/agent.py` | LangGraph 흐름: 분류 → 검색 → 답변 → 근거 검사 → (재검색 / 근거 없는 문장 제거) |
| `hive/llm.py` | LLM 선택: Gemini / Claude / Ollama |
| `hive/public_app.py` | 사용자 화면 |
| `hive/admin_app.py` | 관리자 화면(맥 로컬, 볼트 직접 처리) |
| `hive/cloud_app.py` | 배포본: `/` 사용자 + `/admin` 관리자 스냅샷(읽기 전용) |
| `eval/` | RAGAS 질문 세트·실행·보고서 |
| `data/public/` | 공개 내보내기 결과(승인된 위키, 조각, 벡터, 그래프) |

## 실행

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements-dev.txt
cp .env.example .env        # 키는 여기에만 (GOOGLE_API_KEY 또는 ANTHROPIC_API_KEY, 없으면 Ollama)

./run.sh export             # 볼트 → data/public (볼트가 있는 맥에서만)
./run.sh public             # 사용자 화면 http://127.0.0.1:8010
./run.sh admin              # 관리자 화면 http://127.0.0.1:8110
PYTHONPATH=. .venv/bin/python -m uvicorn hive.cloud_app:app --port 8120   # 배포본과 같은 구성
```

Neo4j: `.env`에 `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`를 넣고 `python -m hive.graphdb sync`.

RAGAS:

```bash
python -m eval.make_testset      # 질문 세트 (사람이 검토 후 확정)
python -m eval.run_ragas answer  # 방식별 답
python -m eval.run_ragas score   # 채점
python -m eval.run_ragas report  # eval/report.md
```

## 배포 (Render, 무료)

`render.yaml` + `Dockerfile`. Render에서 이 저장소를 연결하고, 비밀 변수 `ADMIN_PASSWORD`, `GOOGLE_API_KEY`를 넣는다.
배포본은 볼트 없이 `data/public/`만 쓴다.

## 공개 범위

이 저장소에는 앱 코드와 **승인된 위키 내보내기**만 있다. 원문 사본(`raw/`), 사내 자료(`workspaces/`), API 키·토큰은 포함하지 않는다.
위키 문서는 공개 자료를 한국어로 정리한 것이며, 각 문서에 원문 링크와 출처가 있다.
