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

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
