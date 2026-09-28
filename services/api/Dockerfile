FROM python:3.12.8-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY services/api/pyproject.toml ./
RUN pip install --no-cache-dir '.[dev]'
COPY services/api/alembic.ini ./
COPY services/api/alembic ./alembic
COPY services/api/app ./app
COPY services/api/tests ./tests
COPY contracts /contracts
COPY tests/fixtures /fixtures
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
