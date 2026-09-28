#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
  echo "Execute com sudo: sudo sh deploy/production/stage-production.sh" >&2
  exit 1
fi

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
SOURCE_DIR=$PROJECT_DIR/deploy/production
INSTALL_DIR=/opt/homelab/finance
ENV_FILE=$INSTALL_DIR/finance.env
BACKUP_ROOT=/backup/finance

install -d -m 750 -o root -g root "$INSTALL_DIR"
install -d -m 750 -o root -g root "$BACKUP_ROOT"
install -m 640 -o root -g root \
  "$SOURCE_DIR/compose.production.example.yml" "$INSTALL_DIR/compose.yml"
install -m 750 -o root -g root \
  "$SOURCE_DIR/create-finance-database.sh" \
  "$SOURCE_DIR/backup-finance.sh" \
  "$SOURCE_DIR/verify-finance-backup.sh" \
  "$INSTALL_DIR/"

if [ ! -e "$ENV_FILE" ]; then
  DATABASE_PASSWORD=$(openssl rand -hex 32)
  umask 077
  sed \
    -e "s/SENHA_HEXADECIMAL_GERADA/$DATABASE_PASSWORD/g" \
    -e 's/^FINANCE_TELEGRAM_ENABLED=true$/FINANCE_TELEGRAM_ENABLED=false/' \
    -e 's/^FINANCE_TELEGRAM_BOT_TOKEN=.*/FINANCE_TELEGRAM_BOT_TOKEN=/' \
    -e 's/^FINANCE_TELEGRAM_CHAT_ID=.*/FINANCE_TELEGRAM_CHAT_ID=/' \
    -e 's/^FINANCE_PLUGGY_ENABLED=true$/FINANCE_PLUGGY_ENABLED=false/' \
    -e 's/^FINANCE_PLUGGY_CLIENT_ID=.*/FINANCE_PLUGGY_CLIENT_ID=/' \
    -e 's/^FINANCE_PLUGGY_CLIENT_SECRET=.*/FINANCE_PLUGGY_CLIENT_SECRET=/' \
    "$SOURCE_DIR/finance.env.example" > "$ENV_FILE"
  unset DATABASE_PASSWORD
  chmod 600 "$ENV_FILE"
  chown root:root "$ENV_FILE"
fi

docker compose -f "$INSTALL_DIR/compose.yml" config --quiet
echo "Produção preparada em $INSTALL_DIR; nenhum serviço foi iniciado."
echo "Preencha Telegram e Pluggy em $ENV_FILE antes do corte."
