FROM python:3.13-alpine@sha256:2d9aefe2fef018a7eb2c13064c89c71929800fd2e5dccdbf52ea5da5bb8d929a

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

COPY src/netbird_gitops /app/netbird_gitops

USER 65532:65532
ENTRYPOINT ["python", "-m", "netbird_gitops"]
