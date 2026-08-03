FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir "fastapi>=0.110" "uvicorn>=0.29" "httpx>=0.27" "aiosqlite>=0.20" "mcp>=2.0,<3"
RUN pip install --no-cache-dir pyyaml

COPY backend/ backend/
COPY frontend/dist/ frontend/dist/
COPY skills/ skills/
COPY scripts/ scripts/

RUN mkdir -p /data

ENV DB_PATH=/data/meeting-agent.db
ENV PORT=9100
EXPOSE 9100

COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

CMD ["./entrypoint.sh"]
