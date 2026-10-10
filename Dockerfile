FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY policies ./policies
COPY apps ./apps
COPY examples ./examples

# Add llm-cpu (needs build-essential + cmake) or ml once those components land.
ARG EXTRAS="api,ui"
RUN uv pip install --system --no-cache ".[${EXTRAS}]"

ENV VIVEKA_POLICY=/app/policies/default.toml
EXPOSE 8000
ENTRYPOINT ["viveka"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000"]
