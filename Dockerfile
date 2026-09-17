FROM python:3.11-slim AS compiler
WORKDIR /workspace

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.11-slim AS production-runtime
WORKDIR /runtime

COPY --from=compiler /root/.local /root/.local
COPY . .

ENV PATH=/root/.local/bin:$PATH
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["gunicorn", "--workers=4", "--threads=2", "--bind=0.0.0.0:8080", "app:create_app()"]
