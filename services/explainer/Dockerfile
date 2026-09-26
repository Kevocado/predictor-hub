FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY explainer ./explainer
RUN uv sync --frozen --no-dev
ENV EXPLAINER_DB_PATH=/data/explainer.sqlite
VOLUME /data
EXPOSE 8090
CMD ["uv", "run", "--no-dev", "uvicorn", "--factory", "explainer.app:create_app", "--host", "0.0.0.0", "--port", "8090"]
