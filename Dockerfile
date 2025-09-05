# syntax=docker/dockerfile:1

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /opt/storycraftr

# System deps (minimal). Optional TeX/Pandoc controlled by build arg
ARG INCLUDE_TEX=false
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
      ca-certificates curl git sed && \
    if [ "$INCLUDE_TEX" = "true" ]; then \
      apt-get install -y --no-install-recommends pandoc texlive-latex-recommended texlive-latex-extra texlive-fonts-recommended texlive-xetex makeindex biber && \
      rm -rf /var/lib/apt/lists/*; \
    else \
      rm -rf /var/lib/apt/lists/*; \
    fi

# Install Python dependencies and the package
COPY pyproject.toml README.md ./
COPY storycraftr ./storycraftr

RUN pip install --upgrade pip && \
    pip install .

# Workspace for user content (mounted via volume)
WORKDIR /workspace

# Entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/entrypoint.sh && chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 7860

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["--help"]
