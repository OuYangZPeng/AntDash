#!/usr/bin/env bash
# AntDash backend one-shot deploy script (for Tencent Cloud / overseas lightweight server).
#
# Usage:
#   ssh root@<server-ip>
#   bash <(curl -sSL https://raw.githubusercontent.com/OuYangZPeng/AntDash/main/deploy/setup_server.sh) \
#        --domain www.antdash.com
#
# Or copy this file to the server and run it directly.
set -euo pipefail

# ---------------------------------------------------------------------------
# Config (override with flags)
# ---------------------------------------------------------------------------
DOMAIN=""
INSTALL_DIR="/opt/AntDash"
PORT=8080
REPO_HTTPS="https://github.com/OuYangZPeng/AntDash.git"
USE_HTTPS_REPO=1   # clone via https (no GitHub SSH key needed on server)

while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain) DOMAIN="$2"; shift 2 ;;
    --dir)    INSTALL_DIR="$2"; shift 2 ;;
    --port)   PORT="$2"; shift 2 ;;
    --ssh-repo) USE_HTTPS_REPO=0; shift ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$DOMAIN" ]]; then
  echo "ERROR: --domain is required (e.g. --domain www.antdash.com)" >&2
  exit 1
fi

echo "==> Deploying AntDash backend"
echo "    domain : $DOMAIN"
echo "    dir    : $INSTALL_DIR"
echo "    port   : $PORT"

# ---------------------------------------------------------------------------
# 1. System dependencies
# ---------------------------------------------------------------------------
echo "==> Installing system packages..."
apt-get update -y
apt-get install -y -q python3-venv python3-pip git nginx \
  certbot python3-certbot-nginx curl

# ---------------------------------------------------------------------------
# 2. Clone repo
# ---------------------------------------------------------------------------
if [[ -d "$INSTALL_DIR" ]]; then
  echo "==> $INSTALL_DIR already exists, pulling latest..."
  git -C "$INSTALL_DIR" pull --ff-only || true
else
  echo "==> Cloning repo..."
  if [[ "$USE_HTTPS_REPO" -eq 1 ]]; then
    git clone "$REPO_HTTPS" "$INSTALL_DIR"
  else
    git clone git@github.com:OuYangZPeng/AntDash.git "$INSTALL_DIR"
  fi
fi

BACKEND_DIR="$INSTALL_DIR/backend"

# ---------------------------------------------------------------------------
# 3. Python venv + deps + seed
# ---------------------------------------------------------------------------
echo "==> Setting up Python venv..."
if [[ ! -d "$BACKEND_DIR/.venv" ]]; then
  python3 -m venv "$BACKEND_DIR/.venv"
fi
# shellcheck disable=SC1091
source "$BACKEND_DIR/.venv/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet -r "$BACKEND_DIR/requirements.txt"
python "$BACKEND_DIR/seed.py" || true   # seed demo data (best-effort)

# ---------------------------------------------------------------------------
# 4. systemd service
# ---------------------------------------------------------------------------
echo "==> Installing systemd service..."
export ANTDASH_PORT="$PORT"   # reference inside the unit file below
envsubst '${INSTALL_DIR} ${PORT}' > /etc/systemd/system/antdash.service \
  < "$INSTALL_DIR/deploy/antdash.service.template"

systemctl daemon-reload
systemctl enable --now antdash
sleep 2
if systemctl is-active --quiet antdash; then
  echo "    antdash service: ACTIVE"
else
  echo "    WARNING: antdash service not active, check: journalctl -u antdash" >&2
fi

# ---------------------------------------------------------------------------
# 5. Nginx reverse proxy (HTTP first; certbot will upgrade to HTTPS)
# ---------------------------------------------------------------------------
echo "==> Configuring Nginx..."
envsubst '${DOMAIN}' > /etc/nginx/sites-available/antdash \
  < "$INSTALL_DIR/deploy/nginx-antdash.conf.template"
ln -sf /etc/nginx/sites-available/antdash /etc/nginx/sites-enabled/antdash
# remove default site to avoid conflicts
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

# ---------------------------------------------------------------------------
# 6. HTTPS (Let's Encrypt) — overseas server, no ICP filing needed
# ---------------------------------------------------------------------------
echo "==> Requesting Let's Encrypt certificate for $DOMAIN ..."
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos \
  -m "admin@${DOMAIN#*.}" --redirect || {
    echo "    WARNING: certbot failed. Check DNS A record points to this server." >&2
    echo "    The site is still served over HTTP on port 80." >&2
  }

# ---------------------------------------------------------------------------
# 7. Verify
# ---------------------------------------------------------------------------
echo "==> Health check (local)..."
curl -fsS "http://127.0.0.1:${PORT}/docs" >/dev/null && echo "    backend OK (127.0.0.1:$PORT)" \
  || echo "    backend NOT reachable on 127.0.0.1:$PORT"

echo ""
echo "==> Done. Open https://$DOMAIN/docs in your browser."
echo "    If DNS is not yet pointed here, it will only be reachable via HTTP IP."
