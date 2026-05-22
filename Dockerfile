FROM python:3.13-slim

# uv is the project's package manager
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies first (cached layer unless pyproject.toml/uv.lock change)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy project source
COPY src/ ./src/
COPY sql/ ./sql/
COPY main.py .

# data/ and logs/ are mounted as volumes at runtime (see docker-compose.yml)

CMD ["uv", "run", "python", "main.py"]
