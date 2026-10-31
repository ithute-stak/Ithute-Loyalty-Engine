FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml ./
COPY loyalty_api ./loyalty_api
COPY migrations ./migrations
COPY alembic.ini ./
RUN pip install --no-cache-dir .
RUN useradd --create-home --uid 10001 loyalty
USER loyalty
EXPOSE 8000
CMD ["uvicorn", "loyalty_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
