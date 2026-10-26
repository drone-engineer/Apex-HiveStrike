# 배포용: 사용자 화면(/) + 관리자 스냅샷(/admin). 볼트 없이 data/public/만 쓴다.
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 FASTEMBED_CACHE_PATH=/app/.fastembed

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY hive ./hive
COPY data/public ./data/public
# 임베딩 모델을 이미지에 미리 받아 둔다 (첫 요청이 느려지지 않게)
RUN python -c "from hive import index; index.embedder()"

ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn hive.cloud_app:app --host 0.0.0.0 --port ${PORT}"]
