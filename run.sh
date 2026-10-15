#!/usr/bin/env bash

# Always work from the folder this script lives in (same folder as script.py)
cd "$(dirname "$(readlink -f "$0")")" || exit 1

# ---------- 1. Check for python3 / python ----------
find_python() {
    if command -v python3 >/dev/null 2>&1; then
        PY=python3
    elif command -v python >/dev/null 2>&1; then
        PY=python
    else
        PY=""
    fi
}

install_python() {
    echo "[!] Python not found. Trying to install..."

    SUDO=""
    if [ "$(id -u)" -ne 0 ]; then
        if command -v sudo >/dev/null 2>&1; then
            SUDO="sudo"
        else
            echo "[x] Not root and sudo is not available. Cannot install Python."
            return 1
        fi
    fi

    if command -v apt-get >/dev/null 2>&1; then
        $SUDO apt-get update && $SUDO apt-get install -y python3 python3-pip
    elif command -v dnf >/dev/null 2>&1; then
        $SUDO dnf install -y python3 python3-pip
    elif command -v yum >/dev/null 2>&1; then
        $SUDO yum install -y python3 python3-pip
    elif command -v pacman >/dev/null 2>&1; then
        $SUDO pacman -Sy --noconfirm python python-pip
    elif command -v zypper >/dev/null 2>&1; then
        $SUDO zypper install -y python3 python3-pip
    elif command -v apk >/dev/null 2>&1; then
        $SUDO apk add python3 py3-pip
    elif command -v brew >/dev/null 2>&1; then
        brew install python
    else
        echo "[x] No supported package manager found."
        return 1
    fi
}

find_python
if [ -z "$PY" ]; then
    if ! install_python; then
        echo "[x] Failed to install Python. Stopping."
        exit 1
    fi
    find_python
    if [ -z "$PY" ]; then
        echo "[x] Python still not found after install. Stopping."
        exit 1
    fi
fi
echo "[+] Using: $($PY --version 2>&1) ($PY)"

# ---------- 2. Make sure pip is available (errors here don't stop the script) ----------
if ! $PY -m pip --version >/dev/null 2>&1; then
    echo "[!] pip not found, trying ensurepip..."
    $PY -m ensurepip --upgrade >/dev/null 2>&1 || echo "[!] Could not set up pip. Continuing anyway."
fi

# ---------- 3. Install / update requests (errors here don't stop the script) ----------
pip_install() {
    # Try normal, then --user, then --break-system-packages (for PEP 668 systems)
    $PY -m pip install --upgrade requests 2>/dev/null \
        || $PY -m pip install --upgrade --user requests 2>/dev/null \
        || $PY -m pip install --upgrade --break-system-packages requests
}

if $PY -c "import requests" >/dev/null 2>&1; then
    CURRENT=$($PY -c "import requests; print(requests.__version__)")
    echo "[+] requests is installed (v$CURRENT). Checking for updates..."
    if pip_install; then
        NEW=$($PY -c "import requests; print(requests.__version__)")
        if [ "$CURRENT" != "$NEW" ]; then
            echo "[+] requests updated: v$CURRENT -> v$NEW"
        else
            echo "[+] requests is already up to date."
        fi
    else
        echo "[!] Could not update requests. Continuing with v$CURRENT."
    fi
else
    echo "[!] requests not installed. Installing..."
    if pip_install; then
        echo "[+] requests installed."
    else
        echo "[!] Failed to install requests. Continuing anyway."
    fi
fi

# ---------- 4. Run script.py ----------
if [ ! -f "script.py" ]; then
    echo "[x] script.py not found in $(pwd)"
    exit 1
fi

echo "[+] Running script.py..."
exec $PY script.py "$@"
