# syntax=docker/dockerfile:1.7
FROM mcr.microsoft.com/azurelinux/base/python:3.12 AS base

# Install uv (Astral) for fast deterministic deps.
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    mv /root/.local/bin/uv /usr/local/bin/uv

WORKDIR /app

# Bring the aks-mcp binary into the image so the agent can spawn it as a child.
ARG AKS_MCP_VERSION=v0.0.18
RUN curl -sL "https://github.com/Azure/aks-mcp/releases/download/${AKS_MCP_VERSION}/aks-mcp-linux-amd64" \
        -o /usr/local/bin/aks-mcp && \
    chmod +x /usr/local/bin/aks-mcp

# Dependencies first, for cache friendliness.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY src/ ./src/
COPY prompts/ ./prompts/

# Non-root + read-only filesystem at deploy time (Helm template sets that).
RUN adduser --uid 1000 --disabled-password --gecos "" meshops && \
    chown -R meshops:meshops /app
USER 1000

EXPOSE 9464

CMD ["uv", "run", "--no-sync", "python", "-m", "stewards.inference"]
