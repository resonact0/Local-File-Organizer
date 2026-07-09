#!/usr/bin/env bash
# Launcher for the Local File Organizer.
#
# Usage:
#   ./run.sh <folder-to-organize> [output-folder]
#
# Sets up the Python virtual environment (first run only), makes sure Ollama
# is installed/running with the required models, then runs main.py against
# the folder you pass in.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ $# -lt 1 ]; then
    echo "Usage: $0 <folder-to-organize> [output-folder]"
    exit 1
fi

INPUT_DIR="$1"
OUTPUT_DIR="${2:-}"

if [ ! -d "$INPUT_DIR" ]; then
    echo "Error: '$INPUT_DIR' is not a directory."
    exit 1
fi

# Run everything at low priority so the AI models don't starve the rest of
# the machine (falls back to no-op prefixes if these tools aren't present).
NICE_CPU=()
if command -v nice &> /dev/null; then
    NICE_CPU=(nice -n 15)
fi
if command -v ionice &> /dev/null; then
    NICE_CPU=(ionice -c2 -n7 "${NICE_CPU[@]}")
fi

# Warn (and let the user bail) if there isn't enough free memory to safely
# load the models — avoids triggering the OOM killer / a system freeze.
MIN_FREE_MB=2048
check_memory() {
    local avail_mb=""
    if command -v free &> /dev/null; then
        avail_mb=$(free -m | awk '/^Mem:/{print $7}')
    elif command -v vm_stat &> /dev/null; then
        avail_mb=$(vm_stat | awk '/Pages free/{gsub("\\.",""); print int($3*4096/1024/1024)}')
    fi
    if [ -n "$avail_mb" ] && [ "$avail_mb" -lt "$MIN_FREE_MB" ]; then
        echo "Warning: only ~${avail_mb}MB of free memory available."
        echo "Loading the AI models with this little headroom risks freezing/crashing your system."
        read -r -p "Continue anyway? (y/N): " reply
        case "$reply" in
            [yY]|[yY][eE][sS]) ;;
            *) echo "Aborting."; exit 1 ;;
        esac
    fi
}
check_memory

# --- Python virtual environment -------------------------------------------
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi
# shellcheck disable=SC1091
source venv/bin/activate

echo "Checking Python dependencies..."
pip install -q -r requirements.txt

# --- Ollama ------------------------------------------------------------
# Prefer a local `ollama` CLI; fall back to a running "ollama" Docker
# container (e.g. `docker run -d --name ollama -p 11434:11434 ollama/ollama`).
OLLAMA_CLI=()
if command -v ollama &> /dev/null; then
    OLLAMA_CLI=(ollama)
elif command -v docker &> /dev/null && docker ps --format '{{.Names}}' 2>/dev/null | grep -qx ollama; then
    OLLAMA_CLI=(docker exec ollama ollama)
fi

OLLAMA_STARTED_BY_SCRIPT=false
OLLAMA_PID=""

stop_ollama_if_we_started_it() {
    if [ "$OLLAMA_STARTED_BY_SCRIPT" = true ] && [ -n "$OLLAMA_PID" ]; then
        echo "Stopping Ollama server (started by this script)..."
        kill "$OLLAMA_PID" 2>/dev/null || true
        wait "$OLLAMA_PID" 2>/dev/null || true
    fi
}
trap stop_ollama_if_we_started_it EXIT

if curl -s -o /dev/null http://localhost:11434/api/version; then
    echo "Ollama server already running, reusing it."
elif [ ${#OLLAMA_CLI[@]} -eq 0 ]; then
    echo "Error: Ollama is not installed and no server is reachable at localhost:11434."
    echo "Install it from https://ollama.com, run it via Docker (--name ollama), and try again."
    exit 1
else
    echo "Starting Ollama server..."
    # Cap concurrency so at most one model is resident and one request runs
    # at a time — this bounds RAM/VRAM/CPU usage instead of letting Ollama
    # load both models and serve requests in parallel.
    nohup env OLLAMA_MAX_LOADED_MODELS=1 OLLAMA_NUM_PARALLEL=1 OLLAMA_MAX_QUEUE=1 \
        "${NICE_CPU[@]}" "${OLLAMA_CLI[@]}" serve > /tmp/ollama-serve.log 2>&1 &
    OLLAMA_PID=$!
    OLLAMA_STARTED_BY_SCRIPT=true
    for _ in $(seq 1 15); do
        curl -s -o /dev/null http://localhost:11434/api/version && break
        sleep 1
    done
fi

for model in llama3.2:3b llava:7b; do
    if [ ${#OLLAMA_CLI[@]} -gt 0 ]; then
        if ! "${OLLAMA_CLI[@]}" list | awk '{print $1}' | grep -qx "$model"; then
            echo "Pulling model $model (first run only)..."
            "${OLLAMA_CLI[@]}" pull "$model"
        fi
    elif ! curl -s http://localhost:11434/api/tags | grep -q "\"name\":\"$model\""; then
        echo "Warning: model $model not found and no Ollama CLI available to pull it."
    fi
done

# --- Run -------------------------------------------------------------------
"${NICE_CPU[@]}" python main.py "$INPUT_DIR" "$OUTPUT_DIR"
