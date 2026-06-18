FROM python:3.14-slim AS builder

WORKDIR /build

# Build tools needed to compile the project wheel
RUN pip install --no-cache-dir --upgrade pip setuptools wheel build

COPY pyproject.toml MANIFEST.in README.md ./
COPY cli/ cli/
COPY engine/ engine/
COPY config/ config/
COPY docs/man/ docs/man/

# Build a wheel and install it to a clean prefix
RUN python -m build --wheel --outdir /dist
RUN pip install --no-cache-dir ".[api]" --target=/install


# ──────── Runtime ────────
FROM python:3.14-slim

# Create a non-root user and group
RUN groupadd --system --gid 999 conductor && \
    useradd --system --gid conductor --uid 999 --no-create-home --home-dir /var/lib/conductor conductor

# Create data directories
RUN mkdir -p /var/lib/conductor /etc/conductor && \
    chown -R conductor:conductor /var/lib/conductor

# Install from builder output
COPY --from=builder /install /usr/local

# Runtime user
USER conductor:conductor
WORKDIR /var/lib/conductor

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD python -c "import httpx; httpx.get('http://localhost:8080/v1/health', timeout=5).raise_for_status()"

ENTRYPOINT ["cond"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8080"]
