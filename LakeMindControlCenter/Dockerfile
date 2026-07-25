# syntax=docker/dockerfile:1.7
ARG NODE_IMAGE=node:20-alpine
ARG PYTHON_IMAGE=python:3.12-slim

FROM ${NODE_IMAGE} AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci
COPY frontend/ ./
RUN npm run build

FROM ${PYTHON_IMAGE} AS py-builder
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /uvx /bin/
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 PYTHONDONTWRITEBYTECODE=1 UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
COPY control/pyproject.toml control/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

FROM ${PYTHON_IMAGE} AS runtime
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends nginx supervisor && rm -rf /var/lib/apt/lists/*
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
COPY --from=py-builder /app/.venv /app/.venv
COPY bff/app.py ./bff/app.py
COPY steward/app.py ./steward/app.py
COPY steward/steward_service.py ./steward/steward_service.py
COPY --from=frontend-build /build/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY supervisord.conf /etc/supervisor/conf.d/lakemind.conf
RUN rm -f /etc/nginx/sites-enabled/default
EXPOSE 3000
CMD ["supervisord", "-n", "-c", "/etc/supervisor/conf.d/lakemind.conf"]
