FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim as builder

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .


RUN uv pip install --system --no-cache .

COPY . .


RUN uv pip install --system --no-cache -e .


FROM python:3.12-slim as final

# Install git 
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user for security
RUN useradd --create-home appuser
USER appuser
WORKDIR /home/appuser/app

# Copy the installed dependencies from the builder stage
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/ /usr/local/bin/


COPY --from=builder /app .

CMD ["python", "main.py"]

