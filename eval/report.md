# RAGAS 평가 결과

- 작성: 2026-10-26
- 질문 세트: `eval/testset.json` 27문항 (단일 문서 18, 관계 9)
- 답변 LLM: Ollama gemma4:26b / 채점 LLM: -
- 임베딩: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`

| 방식 | 문서 적중률 | 적중률(관계) | 적중률(단일 문서) | 관계 질문 두 문서 모두 | faithfulness | answer_relevancy | context_precision | context_recall | 평균 시간(초) |
|---|---|---|---|---|---|---|---|---|---|
| 키워드 | 96% | 100% | 94% | 8/9 | - | - | - | - | 6.9 |
| 벡터 | 93% | 100% | 89% | 5/9 | - | - | - | - | 4.8 |
| 키워드+벡터 | 96% | 100% | 94% | 8/9 | - | - | - | - | 6.6 |
| GraphRAG | 100% | 100% | 100% | 9/9 | - | - | - | - | 4.9 |
| GraphRAG + LangGraph 근거 검사 | 100% | 100% | 100% | 9/9 | - | - | - | - | 11.6 |
