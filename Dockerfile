# 배포용: 사용자 화면(/) + 관리자 스냅샷(/admin). 볼트 없이 data/public/만 쓴다.
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY hive ./hive
COPY data/public ./data/public
# 질문 임베딩은 사전을 줄인 경량 모델로 (무료 서버 메모리 512MB — hive/slim_model.py)
COPY data/model ./data/model

ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn hive.cloud_app:app --host 0.0.0.0 --port ${PORT}"]
