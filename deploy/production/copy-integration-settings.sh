#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
  echo "Execute com sudo: sudo sh deploy/production/copy-integration-settings.sh" >&2
  exit 1
fi

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
SOURCE_ENV=$PROJECT_DIR/.env
TARGET_ENV=/opt/homelab/finance/finance.env

test -f "$SOURCE_ENV"
test -f "$TARGET_ENV"

python3 "$PROJECT_DIR/deploy/production/copy-integration-settings.py" \
  --source "$SOURCE_ENV" \
  --target "$TARGET_ENV"
chown root:root "$TARGET_ENV"
chmod 600 "$TARGET_ENV"

echo "Configurações de Telegram e Pluggy copiadas sem exibir os valores."
