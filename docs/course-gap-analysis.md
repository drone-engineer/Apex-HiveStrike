# 과제 요구사항 vs 현재 프로젝트 비교 (2026-10-26)

과제: OpenUp 풀스택B — "오픈소스 AI 자동화 에이전트 프로젝트"
> Obsidian 지식 베이스와 GraphRAG를 결합해 개인 업무를 자동화하는 AI 서비스를 직접 구현·배포
> 최종 산출물: 개인별 배포 가능한 AI 데모 서비스 1종 + PRD 설계 문서 · RAGAS 평가 보고서 · GitHub 공개

## 한눈에

| 단계 | 과제 요구 | 현재 상태 | 판정 |
|---|---|---|---|
| 01 지식 구축 | Obsidian · 데이터 수집/전처리 | 옵시디언 볼트 위키 184건(제품 62·기술 60·회사 17·사업 4·목차 41), raw 원문 사본, 자동 수집 예약 작업 9개, 수집함→승인 게이트, frontmatter 스키마(specs·compatible_with·use_cases), 공개용 내보내기 | ✅ 요구 이상 |
| 02 지능형 검색 | Neo4j · RAG · GraphRAG | 키워드 점수 검색만 있음. 문서 간 위키링크 1,247개, 그래프 712개 연결선(`wiki_graph.py`)은 있으나 Neo4j·임베딩 없음 | ❌ 핵심 공백 |
| 03 에이전트 개발 | LangChain · LangGraph · RAGAS | 웹 답변은 Claude 단일 호출. 수집·작성·검증 에이전트는 Claude Code 서브에이전트라 LangGraph가 아님. RAGAS 평가 없음 | ❌ 공백 |
| 04 서비스 배포 | FastAPI · Docker · HF Spaces | FastAPI 사용자·관리자 화면 완성(로컬 동작 확인). Dockerfile·HF Spaces 미완 | 🟡 절반 |
| 산출물 | PRD · RAGAS 보고서 · GitHub 공개 | 셋 다 없음 (새 앱은 아직 git 저장소 아님) | ❌ |

## 강점 — 과제 주제와 잘 맞는 점
- **"개인 업무 자동화"가 실제로 돌아가고 있다.** 매일 대드론·SBC·항법·펌웨어 릴리스·사업공고·정부과제를 자동 수집하고, 디스코드 수집함에서 승인하면 위키가 된다. 관리자 화면이 이 흐름을 그대로 보여 준다. 데모용 샘플이 아니라 실제 운영 데이터라는 점이 차별점이다.
- **GraphRAG에 쓸 관계가 이미 구조화돼 있다.** 제품 → 제조사(`manufacturer`), 제품 ↔ 호환 부품(`compatible_with`), 문서 → 분야(`category`), 문서 → 출처(`sources`), 본문 위키링크. Neo4j로 바로 옮길 수 있다.
- **근거 규칙이 강하다.** 모든 문장에 각주 출처, 영문 원문 링크, 승인된 문서만 서비스. RAGAS의 faithfulness(근거 충실도) 평가와 잘 맞는다.

## 공백을 메우는 계획

### 02 지능형 검색
1. **Neo4j 적재**: 노드 `Doc(제품·기술·회사·사업)`, `Category`, `Source` / 관계 `MANUFACTURED_BY`, `COMPATIBLE_WITH`, `IN_CATEGORY`, `CITES`(출처), `LINKS_TO`(본문 링크). 배포 환경에서는 Neo4j Aura Free(무료 클라우드)를 쓰거나, Space 안에서는 같은 그래프를 networkx로 들고 있게 한다.
2. **벡터 RAG**: 문서를 절(##) 단위로 나눠 임베딩한다. 다국어 무료 모델(예: `BAAI/bge-m3`, `intfloat/multilingual-e5`)을 쓰면 API 비용이 없다.
3. **GraphRAG**: 벡터 검색 상위 절 → 그래프에서 1~2단계 이웃(제조사·호환 부품·같은 분야)을 확장 → 답변 근거로 넣는다. "6S 모터에 맞는 ESC·프롭" 같은 호환성 질문에서 차이가 드러난다.

### 03 에이전트 (LangGraph)
`질문 분류(추천/비교/사실) → 검색(벡터+그래프) → 답변 작성 → 근거 검사(각주 없는 주장·문서에 없는 수치 → 재검색 또는 "모름")` 흐름을 StateGraph로 고정한다. LLM은 LangChain의 Claude 연결(`langchain-anthropic`)로 쓴다.

### RAGAS 평가
- 위키에서 질문·정답 30개 내외를 만든다(제품 사양, 호환성, 규제 절차, 기술 비교).
- 지표: faithfulness, answer_relevancy, context_precision, context_recall.
- 비교: ① 키워드 검색 ② 벡터 RAG ③ GraphRAG → 보고서에 표로 싣는다.

### 04 배포 · 산출물
- Dockerfile → HF Spaces(사용자 `/`, 관리자 `/admin` 읽기 전용 스냅샷).
- GitHub 공개 저장소에는 **앱 코드 + 공개 내보내기(승인된 위키)만** 올린다. `raw/` 원문 사본, `workspaces/` 사내 자료, 디스코드 토큰은 올리지 않는다.
- PRD: 사용자(드론 엔지니어), 문제, 화면, 데이터 흐름(수집→승인→위키→공개), 비기능(근거·보안·요금 한도).

## 참고: 기존 `drone_engineer_ais` 프로젝트
같은 과제 스택(LangGraph StateGraph, Neo4j 동기화, LightRAG, RAGAS 보고서 스크립트, PRD, HF Spaces 설정, 테스트)이 이미 갖춰져 있다. 다만 지식은 샘플 공책 30여 건이고 LLM은 Grok이다.
→ 두 가지 길이 있다.
- **A안 (추천)**: 새 앱(실제 위키 184건 + 관리자 자동화)을 본체로 두고, `drone_engineer_ais`의 LangGraph·Neo4j·RAGAS 코드를 옮겨 붙인다.
- **B안**: `drone_engineer_ais`를 본체로 두고 지식 소스만 이 볼트의 공개 위키로 바꾼다.
