# syntax=docker/dockerfile:1.7
FROM mcr.microsoft.com/azurelinux/base/python:3.12 AS base

# The azurelinux base image ships without CA certs, so HTTPS downloads (uv,
# aks-mcp) fail SSL verification ("unable to get local issuer certificate").
# It also lacks awk/tar, which the uv install script needs. Install them up front.
RUN tdnf install -y ca-certificates tar gawk shadow-utils && tdnf clean all

# Install uv (Astral) for fast deterministic deps.
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    mv /root/.local/bin/uv /usr/local/bin/uv

WORKDIR /app

# Bring the aks-mcp binary into the image so the agent can spawn it as a child.
ARG AKS_MCP_VERSION=v0.0.18
RUN curl -sL "https://github.com/Azure/aks-mcp/releases/download/${AKS_MCP_VERSION}/aks-mcp-linux-amd64" \
        -o /usr/local/bin/aks-mcp && \
    chmod +x /usr/local/bin/aks-mcp

# Dependencies first, for cache friendliness. README.md is required because
# pyproject.toml declares `readme = "README.md"`. Install deps only (not the
# project itself) here so this layer caches until deps change.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ ./src/
COPY prompts/ ./prompts/

# Now the source is present, install the project (editable) into the venv.
RUN uv sync --frozen --no-dev

# Non-root + read-only filesystem at deploy time (Helm template sets that).
# azurelinux uses shadow-utils' useradd (no Debian `adduser`).
RUN useradd --uid 1000 --create-home --shell /bin/bash meshops && \
    chown -R meshops:meshops /app
USER 1000

EXPOSE 9464

CMD ["uv", "run", "--no-sync", "python", "-m", "stewards.inference"]
