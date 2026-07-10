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

# --- Hard CPU/RAM ceiling ----------------------------------------------
# nice/ionice only *deprioritize* the AI processes; under sustained load they
# can still saturate every core and make the whole desktop unresponsive for
# minutes (this has happened before). Where available, additionally run them
# in a systemd user scope with a real cgroup cap, so the machine stays
# responsive and, worst case, only the AI processes get OOM-killed instead of
# the whole system hanging. Override the defaults with ORGANIZER_CPU_QUOTA /
# ORGANIZER_MEM_MAX / ORGANIZER_MEM_HIGH if you want to tune them.
CPU_CORES=$(nproc 2>/dev/null || echo 4)
QUOTA_CORES=$(( CPU_CORES - 2 ))
[ "$QUOTA_CORES" -ge 1 ] || QUOTA_CORES=1
DEFAULT_CPU_QUOTA="$(( QUOTA_CORES * 100 ))%"

TOTAL_MEM_MB=$(free -m 2>/dev/null | awk '/^Mem:/{print $2}')
DEFAULT_MEM_MAX_MB=$(( ${TOTAL_MEM_MB:-10240} * 60 / 100 ))
DEFAULT_MEM_HIGH_MB=$(( ${TOTAL_MEM_MB:-10240} * 45 / 100 ))
[ "$DEFAULT_MEM_MAX_MB" -ge 3072 ] || DEFAULT_MEM_MAX_MB=3072
[ "$DEFAULT_MEM_HIGH_MB" -ge 2048 ] || DEFAULT_MEM_HIGH_MB=2048

CPU_QUOTA="${ORGANIZER_CPU_QUOTA:-$DEFAULT_CPU_QUOTA}"
MEM_MAX="${ORGANIZER_MEM_MAX:-${DEFAULT_MEM_MAX_MB}M}"
MEM_HIGH="${ORGANIZER_MEM_HIGH:-${DEFAULT_MEM_HIGH_MB}M}"
SCOPE_PROPS=(-p CPUQuota="$CPU_QUOTA" -p MemoryMax="$MEM_MAX" -p MemoryHigh="$MEM_HIGH")

SCOPE_WRAP=()
if command -v systemd-run &> /dev/null && \
   systemd-run --user --scope --quiet "${SCOPE_PROPS[@]}" -- /bin/true &> /dev/null; then
    SCOPE_WRAP=(systemd-run --user --scope --quiet "${SCOPE_PROPS[@]}" --)
    echo "Capping AI processes to CPUQuota=$CPU_QUOTA MemoryMax=$MEM_MAX (MemoryHigh=$MEM_HIGH)."
else
    echo "Note: no systemd user scope available (falling back to nice/ionice only;" \
         "a sustained heavy run can still make the desktop sluggish)."
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
# Prefer a local `ollama` CLI. If that's not installed, fall back to Docker:
# reuse an already-running "ollama" container, start a stopped one, or
# create a brand new one if none exists yet.
OLLAMA_DOCKER_CONTAINER="ollama"
OLLAMA_CLI=()

OLLAMA_STARTED_BY_SCRIPT=false   # we started a native `ollama serve` process
OLLAMA_PID=""
DOCKER_STARTED_BY_SCRIPT=false   # we started/created the docker container

cleanup_ollama() {
    if [ "$OLLAMA_STARTED_BY_SCRIPT" = true ] && [ -n "$OLLAMA_PID" ]; then
        echo "Stopping Ollama server (started by this script)..."
        kill "$OLLAMA_PID" 2>/dev/null || true
        wait "$OLLAMA_PID" 2>/dev/null || true
    fi
    if [ "$DOCKER_STARTED_BY_SCRIPT" = true ]; then
        echo "Stopping Ollama Docker container (started by this script)..."
        docker stop "$OLLAMA_DOCKER_CONTAINER" &> /dev/null || true
    fi
}
trap cleanup_ollama EXIT

if curl -s -o /dev/null http://localhost:11434/api/version; then
    echo "Ollama server already running, reusing it."
    if command -v ollama &> /dev/null; then
        OLLAMA_CLI=(ollama)
    elif command -v docker &> /dev/null && docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$OLLAMA_DOCKER_CONTAINER"; then
        OLLAMA_CLI=(docker exec "$OLLAMA_DOCKER_CONTAINER" ollama)
    fi
elif command -v ollama &> /dev/null; then
    OLLAMA_CLI=(ollama)
    echo "Starting Ollama server..."
    # Cap concurrency so at most one model is resident and one request runs
    # at a time — this bounds RAM/VRAM/CPU usage instead of letting Ollama
    # load both models and serve requests in parallel.
    nohup env OLLAMA_MAX_LOADED_MODELS=1 OLLAMA_NUM_PARALLEL=1 OLLAMA_MAX_QUEUE=1 \
        "${SCOPE_WRAP[@]}" "${NICE_CPU[@]}" "${OLLAMA_CLI[@]}" serve > /tmp/ollama-serve.log 2>&1 &
    OLLAMA_PID=$!
    OLLAMA_STARTED_BY_SCRIPT=true
    for _ in $(seq 1 15); do
        curl -s -o /dev/null http://localhost:11434/api/version && break
        sleep 1
    done
elif command -v docker &> /dev/null; then
    OLLAMA_CLI=(docker exec "$OLLAMA_DOCKER_CONTAINER" ollama)
    if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qx "$OLLAMA_DOCKER_CONTAINER"; then
        echo "Starting existing Ollama Docker container..."
        docker start "$OLLAMA_DOCKER_CONTAINER" > /dev/null
    else
        echo "Creating and starting Ollama Docker container..."
        DOCKER_GPU_FLAGS=()
        if command -v nvidia-smi &> /dev/null; then
            DOCKER_GPU_FLAGS=(--gpus=all)
        fi
        docker run -d --name "$OLLAMA_DOCKER_CONTAINER" \
            -p 11434:11434 \
            -v ollama:/root/.ollama \
            --cpus="$QUOTA_CORES" \
            --memory="$MEM_MAX" \
            "${DOCKER_GPU_FLAGS[@]}" \
            ollama/ollama > /dev/null
    fi
    DOCKER_STARTED_BY_SCRIPT=true
    for _ in $(seq 1 15); do
        curl -s -o /dev/null http://localhost:11434/api/version && break
        sleep 1
    done
else
    echo "Error: Ollama is not installed, Docker is not available, and no server is reachable at localhost:11434."
    echo "Install Ollama from https://ollama.com, or install Docker, and try again."
    exit 1
fi

if ! curl -s -o /dev/null http://localhost:11434/api/version; then
    echo "Error: Ollama server did not become reachable at localhost:11434."
    exit 1
fi

for model in qwen2.5:7b-instruct llava:7b; do
    if [ ${#OLLAMA_CLI[@]} -gt 0 ]; then
        if ! "${OLLAMA_CLI[@]}" list | awk '{print $1}' | grep -qx "$model"; then
            echo "Pulling model $model (first run only)..."
            "${OLLAMA_CLI[@]}" pull "$model"
        fi
    elif ! curl -s http://localhost:11434/api/tags | grep -q "\"name\":\"$model\""; then
        echo "Warning: model $model not found and no Ollama CLI available to pull it."
    fi
done

# --- Nextcloud rescan --------------------------------------------------
# Files under a Nextcloud data directory are indexed in Nextcloud's database;
# edits made directly on disk (like this organizer's copies/moves) stay
# invisible in the Nextcloud UI until `occ files:scan` refreshes the index.
# After a run, rescan any organized path that lives inside the data root.
NEXTCLOUD_CONTAINER="${NEXTCLOUD_CONTAINER:-nextcloud_app}"
NEXTCLOUD_DATA_ROOT="${NEXTCLOUD_DATA_ROOT:-/mnt/data1tb/nextcloud/data}"

nextcloud_container_path() {
    local abs="$1" rel
    case "$abs" in
        "$NEXTCLOUD_DATA_ROOT"/*)
            rel="${abs#"$NEXTCLOUD_DATA_ROOT"}"
            echo "/var/www/html/data$rel"
            ;;
    esac
}

# The organizer runs as the invoking user, so folders it creates under the
# Nextcloud data dir come out user-owned. Nextcloud's PHP process (www-data)
# then has no write bit on them, so moves/renames of that output silently
# fail in the Nextcloud web UI even though occ files:scan shows it fine.
# Fix that up so the UI can manage the organized output going forward.
nextcloud_fix_ownership() {
    local path abs cpath
    command -v docker &> /dev/null || return 0
    docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$NEXTCLOUD_CONTAINER" || return 0
    for path in "$@"; do
        [ -n "$path" ] && [ -e "$path" ] || continue
        abs=$(readlink -f "$path")
        cpath=$(nextcloud_container_path "$abs") || continue
        [ -n "$cpath" ] || continue
        docker exec -u root "$NEXTCLOUD_CONTAINER" chgrp -R www-data "$cpath" && \
        docker exec -u root "$NEXTCLOUD_CONTAINER" chmod -R g+w "$cpath" || \
            echo "Warning: could not fix Nextcloud ownership for $cpath (run it manually)."
    done
}

nextcloud_scan() {
    local path abs rel
    command -v docker &> /dev/null || return 0
    docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$NEXTCLOUD_CONTAINER" || return 0
    for path in "$@"; do
        [ -n "$path" ] && [ -e "$path" ] || continue
        abs=$(readlink -f "$path")
        case "$abs" in
            "$NEXTCLOUD_DATA_ROOT"/*)
                rel="${abs#"$NEXTCLOUD_DATA_ROOT"}"
                echo "Rescanning $rel in Nextcloud..."
                docker exec -u www-data "$NEXTCLOUD_CONTAINER" php occ files:scan --path="$rel" || \
                    echo "Warning: Nextcloud rescan failed for $rel (run it manually)."
                ;;
        esac
    done
}

# --- Run -------------------------------------------------------------------
"${SCOPE_WRAP[@]}" "${NICE_CPU[@]}" python main.py "$INPUT_DIR" "$OUTPUT_DIR"

nextcloud_fix_ownership "$OUTPUT_DIR"
nextcloud_scan "$INPUT_DIR" "$OUTPUT_DIR"
