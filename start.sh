#!/usr/bin/env bash
# start.sh — Full Seshat setup and launch script
# Run with: bash start.sh
set -euo pipefail

# ── Colours ────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[seshat]${NC} $*"; }
warn()  { echo -e "${YELLOW}[seshat]${NC} $*"; }
error() { echo -e "${RED}[seshat]${NC} $*" >&2; exit 1; }

# ── 1. System requirements ─────────────────────────────────────────────────
info "Checking system requirements..."
if ! command -v curl &>/dev/null; then
    info "curl not found — installing..."
    if command -v apt-get &>/dev/null; then
        sudo apt-get install -y curl
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y curl
    elif command -v yum &>/dev/null; then
        sudo yum install -y curl
    else
        error "Cannot install curl automatically. Please install it manually and re-run."
    fi
fi

# ── 2. Python venv ────────────────────────────────────────────────────────
info "Checking Python environment..."
command -v python3 &>/dev/null || error "python3 not found. Install Python 3.11+."

if [ ! -d ".venv" ]; then
    info "Creating virtual environment..."
    python3 -m venv .venv
else
    info "Virtual environment already exists, skipping creation."
fi

PYTHON=".venv/bin/python"
PIP=".venv/bin/pip"

# ── 2. Install dependencies ────────────────────────────────────────────────
info "Installing dependencies..."
"$PIP" install --quiet -e ".[dev]"
info "Dependencies installed."

# ── 3. Docker Compose (Ollama + Open-WebUI) ────────────────────────────────
info "Starting Docker services (Ollama + Open-WebUI)..."
command -v docker &>/dev/null || error "Docker not found. Install Docker: https://docs.docker.com/engine/install/"

if ! docker info &>/dev/null; then
    error "Cannot reach the Docker daemon. Fix with:
    sudo usermod -aG docker \$USER
  Then log out and back in (or run: newgrp docker), and re-run this script."
fi

docker compose up -d

# ── 4. Wait for Ollama ─────────────────────────────────────────────────────
info "Waiting for Ollama to be ready..."
MAX_WAIT=120
ELAPSED=0
until curl -sf http://localhost:11434/api/tags &>/dev/null; do
    if [ "$ELAPSED" -ge "$MAX_WAIT" ]; then
        error "Ollama did not start within ${MAX_WAIT}s. Check: docker compose logs ollama"
    fi
    sleep 2
    ELAPSED=$((ELAPSED + 2))
done
info "Ollama is ready."

# ── 5. Pull the LLM model (skip if already present) ───────────────────────
MODEL="llama3.1:8b"
info "Checking for model ${MODEL}..."
if docker compose exec -T ollama ollama list 2>/dev/null | grep -q "${MODEL}"; then
    info "Model ${MODEL} already pulled, skipping."
else
    info "Pulling ${MODEL} — this may take several minutes on first run..."
    docker compose exec -T ollama ollama pull "${MODEL}"
    info "Model pulled."
fi

# ── 6. Start Seshat server ─────────────────────────────────────────────────
echo ""
info "=========================================="
info " Seshat is starting on http://0.0.0.0:8000"
info ""
info " Open-WebUI → http://localhost:3000"
info " API docs   → http://localhost:8000/docs"
info ""
info " To ingest your alerts:"
info "   .venv/bin/python scripts/ingest.py ingest config/sources/<your_source>.yaml"
info ""
info " Add to Open-WebUI (Admin → Settings → Connections → OpenAI API):"
info "   URL : http://host.docker.internal:8000/v1"
info "   Key : seshat"
info "=========================================="
echo ""

"$PYTHON" -m seshat
