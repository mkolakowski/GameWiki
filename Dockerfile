FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

# Dependency layer first so source edits don't reinstall the world.
COPY pyproject.toml ./
COPY app/version.py ./app/version.py
RUN pip install --no-cache-dir -e ".[dev]"

COPY app ./app
COPY tests ./tests
COPY devtools ./devtools

# Reader-facing docs are served at /docs, so they have to be in the image.
# app/docs.py reads them by allowlisted slug — see DOCS there.
COPY README.md CHANGELOG.md CLAUDE.md ./
COPY docs ./docs

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
