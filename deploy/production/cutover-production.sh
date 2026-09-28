#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
  echo "Execute com sudo: sudo sh deploy/production/cutover-production.sh" >&2
  exit 1
fi

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
INSTALL_DIR=/opt/homelab/finance
ENV_FILE=$INSTALL_DIR/finance.env
COMPOSE_FILE=$INSTALL_DIR/compose.yml
BACKUP_ROOT=/backup/finance
MIGRATION_DIR=$BACKUP_ROOT/migration-$(date -u +%Y%m%dT%H%M%SZ)
HOMELAB_CADDY=/opt/homelab/config/caddy/Caddyfile
HOMELAB_AUTHELIA=/opt/homelab/config/authelia/configuration.yml
DOMAIN=${FINANCE_DOMAIN:-finance.example.com}
LOCAL_WORKER_STOPPED=0
PRODUCTION_WORKER_STARTED=0

rollback_worker() {
  if [ "$LOCAL_WORKER_STOPPED" -eq 1 ] && [ "$PRODUCTION_WORKER_STARTED" -eq 0 ]; then
    docker compose -f "$COMPOSE_FILE" stop worker >/dev/null 2>&1 || true
    (cd "$PROJECT_DIR" && docker compose start worker) >/dev/null 2>&1 || true
  fi
}

restore_proxy_configs() {
  if [ -f "$MIGRATION_DIR/Caddyfile.before" ]; then
    cat "$MIGRATION_DIR/Caddyfile.before" > "$HOMELAB_CADDY"
  fi
  if [ -f "$MIGRATION_DIR/authelia.before.yml" ]; then
    cp -a "$MIGRATION_DIR/authelia.before.yml" "$HOMELAB_AUTHELIA"
  fi
}

trap rollback_worker EXIT HUP INT TERM

test -f "$ENV_FILE"
test -f "$COMPOSE_FILE"
test -f "$HOMELAB_CADDY"
test -f "$HOMELAB_AUTHELIA"
docker compose -f "$COMPOSE_FILE" config --quiet
set -a
. "$ENV_FILE"
set +a

: "${FINANCE_DATABASE_URL:?FINANCE_DATABASE_URL ausente}"
: "${FINANCE_DB_PASSWORD:?FINANCE_DB_PASSWORD ausente}"
: "${FINANCE_TELEGRAM_BOT_TOKEN:?Telegram ainda não configurado}"
: "${FINANCE_TELEGRAM_CHAT_ID:?Telegram ainda não configurado}"
: "${FINANCE_PLUGGY_CLIENT_ID:?Pluggy ainda não configurada}"
: "${FINANCE_PLUGGY_CLIENT_SECRET:?Pluggy ainda não configurada}"
[ "${FINANCE_TELEGRAM_ENABLED:-false}" = true ]
[ "${FINANCE_PLUGGY_ENABLED:-false}" = true ]
[ "${FINANCE_ENVIRONMENT:-}" = production ]
[ "${FINANCE_CORS_ORIGINS:-}" = "https://$DOMAIN" ]
case "$FINANCE_TELEGRAM_BOT_TOKEN:$FINANCE_PLUGGY_CLIENT_ID:$FINANCE_PLUGGY_CLIENT_SECRET" in
  *FICTICIO*|*ficticio*|*00000000-0000-0000-0000-000000000000*)
    echo "O arquivo finance.env ainda contém valores fictícios." >&2
    exit 1
    ;;
esac

install -d -m 750 -o root -g root "$MIGRATION_DIR"
cp -a "$HOMELAB_CADDY" "$MIGRATION_DIR/Caddyfile.before"
cp -a "$HOMELAB_AUTHELIA" "$MIGRATION_DIR/authelia.before.yml"

(cd "$PROJECT_DIR" && docker compose stop worker)
LOCAL_WORKER_STOPPED=1

DUMP_FILE=$MIGRATION_DIR/finance-local.dump
docker exec finance-system-db-1 sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-acl' \
  > "$DUMP_FILE"
docker exec -i postgres pg_restore --list < "$DUMP_FILE" >/dev/null
sha256sum "$DUMP_FILE" > "$DUMP_FILE.sha256"
chown root:root "$DUMP_FILE" "$DUMP_FILE.sha256"
chmod 640 "$DUMP_FILE" "$DUMP_FILE.sha256"

"$INSTALL_DIR/create-finance-database.sh" "$ENV_FILE"
EXISTING_TABLE=$(docker exec postgres sh -c \
  'psql -U "$POSTGRES_USER" -d finance -Atc "SELECT coalesce(to_regclass('"'"'public.transactions'"'"')::text, '"'"''"'"')"')
if [ -n "$EXISTING_TABLE" ]; then
  echo "O banco finance já contém tabelas; restauração automática recusada." >&2
  exit 1
fi

docker exec -i postgres sh -c \
  'pg_restore -U "$POSTGRES_USER" -d finance --role=finance_app --no-owner --no-acl --exit-on-error' \
  < "$DUMP_FILE"

docker compose -f "$COMPOSE_FILE" up -d api web
ATTEMPT=0
until curl --fail --silent --show-error http://127.0.0.1:18000/api/v1/health/ready >/dev/null; do
  ATTEMPT=$((ATTEMPT + 1))
  if [ "$ATTEMPT" -ge 30 ]; then
    echo "A API de produção não ficou pronta." >&2
    exit 1
  fi
  sleep 2
done

SOURCE_COUNT=$(docker exec finance-system-db-1 sh -c \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT count(*) FROM transactions"')
TARGET_COUNT=$(docker exec postgres sh -c \
  'psql -U "$POSTGRES_USER" -d finance -Atc "SELECT count(*) FROM transactions"')
if [ "$SOURCE_COUNT" != "$TARGET_COUNT" ]; then
  echo "Contagem divergente após restauração; corte interrompido." >&2
  exit 1
fi

docker compose -f "$COMPOSE_FILE" up -d worker
PRODUCTION_WORKER_STARTED=1

FINANCE_API_URL=http://127.0.0.1:18000 sh "$PROJECT_DIR/deploy/install-hermes-mcp.sh"

"$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/deploy/production/merge-homelab-config.py" \
  --caddy "$HOMELAB_CADDY" \
  --authelia "$HOMELAB_AUTHELIA" \
  --domain "$DOMAIN"

if ! docker exec authelia authelia config validate --config /config/configuration.yml; then
  restore_proxy_configs
  exit 1
fi
if ! docker exec caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile; then
  restore_proxy_configs
  exit 1
fi

docker restart authelia >/dev/null
if ! docker exec caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile; then
  restore_proxy_configs
  docker restart authelia >/dev/null || true
  docker exec caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile \
    >/dev/null 2>&1 || true
  exit 1
fi

install -m 644 "$PROJECT_DIR/deploy/production/finance-backup.service.example" \
  /etc/systemd/system/finance-backup.service
install -m 644 "$PROJECT_DIR/deploy/production/finance-backup.timer.example" \
  /etc/systemd/system/finance-backup.timer
systemctl daemon-reload
"$INSTALL_DIR/backup-finance.sh"
systemctl enable --now finance-backup.timer

trap - EXIT HUP INT TERM
echo "Corte concluído. Origem e destino possuem $TARGET_COUNT transações."
