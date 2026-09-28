#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
  echo "Execute com sudo: sudo sh deploy/install-hermes-mcp.sh" >&2
  exit 1
fi

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
HERMES_HOME=/home/hermes
INSTALL_DIR=$HERMES_HOME/.local/share/finance-mcp
VENV_DIR=$INSTALL_DIR/.venv
CONFIG_PATH=$HERMES_HOME/.hermes/config.yaml
HERMES_UID=$(id -u hermes)
FINANCE_API_URL=${FINANCE_API_URL:-http://127.0.0.1:8000}

test -f "$CONFIG_PATH"
test -S /run/user/$HERMES_UID/bus

if ! python3 -m ensurepip --version >/dev/null 2>&1; then
  echo "Instalando python3.13-venv, necessário para o ambiente isolado do MCP..."
  DEBIAN_FRONTEND=noninteractive apt-get install -y python3.13-venv
fi

install -d -m 700 -o hermes -g hermes "$INSTALL_DIR"
install -d -m 700 -o hermes -g hermes "$INSTALL_DIR/finance_mcp"
install -m 600 -o hermes -g hermes \
  "$PROJECT_DIR/hermes-mcp/pyproject.toml" "$INSTALL_DIR/pyproject.toml"
install -m 600 -o hermes -g hermes \
  "$PROJECT_DIR/hermes-mcp/finance_mcp/__init__.py" \
  "$PROJECT_DIR/hermes-mcp/finance_mcp/client.py" \
  "$PROJECT_DIR/hermes-mcp/finance_mcp/server.py" \
  "$INSTALL_DIR/finance_mcp/"

if [ ! -x "$VENV_DIR/bin/python" ] || \
  ! runuser -u hermes -- "$VENV_DIR/bin/python" -m pip --version >/dev/null 2>&1; then
  rm -rf "$VENV_DIR"
  if ! runuser -u hermes -- python3 -m venv "$VENV_DIR"; then
    rm -rf "$VENV_DIR"
    echo "Não foi possível criar o ambiente Python isolado." >&2
    echo "No Debian 13, instale: sudo apt install python3.13-venv" >&2
    exit 1
  fi
fi
runuser -u hermes -- "$VENV_DIR/bin/python" -m pip \
  install --disable-pip-version-check "$INSTALL_DIR"

TOKEN_OUTPUT=$(cd "$PROJECT_DIR" && docker compose exec -T api \
  python -m app.integrations.hermes.setup --name hermes-local)
TOKEN=$(printf '%s\n' "$TOKEN_OUTPUT" | sed -n '2p')
unset TOKEN_OUTPUT
case "$TOKEN" in
  fst_*) ;;
  *) echo "A API não retornou um token de serviço válido." >&2; exit 1 ;;
esac

"$VENV_DIR/bin/python" "$PROJECT_DIR/deploy/merge_hermes_mcp.py" \
  --config "$CONFIG_PATH" \
  --token "$TOKEN" \
  --command "$VENV_DIR/bin/finance-hermes-mcp" \
  --api-url "$FINANCE_API_URL"
unset TOKEN
chown hermes:hermes "$CONFIG_PATH"
chmod 600 "$CONFIG_PATH"

runuser -u hermes -- env \
  XDG_RUNTIME_DIR=/run/user/$HERMES_UID \
  DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$HERMES_UID/bus \
  systemctl --user restart hermes-gateway.service

runuser -u hermes -- env \
  XDG_RUNTIME_DIR=/run/user/$HERMES_UID \
  DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$HERMES_UID/bus \
  systemctl --user is-active --quiet hermes-gateway.service

echo "Finance MCP instalado e hermes-gateway.service reiniciado com sucesso."
