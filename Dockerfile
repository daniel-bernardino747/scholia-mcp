FROM ghcr.io/astral-sh/uv:0.11-python3.12-trixie-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_NO_DEV=1

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project

COPY src ./src
RUN uv sync --locked

EXPOSE 8000
CMD ["uv", "run", "--no-sync", "scholia-mcp", "serve"]
