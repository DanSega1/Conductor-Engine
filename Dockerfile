FROM python:3.14-slim

WORKDIR /app

# Build tools needed to compile the project wheel
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

COPY pyproject.toml MANIFEST.in README.md ./
COPY cli/ cli/
COPY engine/ engine/
COPY config/ config/
COPY docs/man/ docs/man/

RUN pip install --no-cache-dir ".[api]"

EXPOSE 8080

CMD ["cond", "serve", "--host", "0.0.0.0", "--port", "8080"]
