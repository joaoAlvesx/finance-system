#!/bin/sh
set -eu

BACKUP_ROOT=${BACKUP_ROOT:-/backup/finance}
TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
TODAY=$(date +%u)
DAY_OF_MONTH=$(date +%d)
DAILY_DIR=$BACKUP_ROOT/daily
WEEKLY_DIR=$BACKUP_ROOT/weekly
MONTHLY_DIR=$BACKUP_ROOT/monthly
TEMP_FILE=$DAILY_DIR/.finance-$TIMESTAMP.dump.tmp
FINAL_FILE=$DAILY_DIR/finance-$TIMESTAMP.dump

umask 027
install -d -m 750 -o root -g root \
  "$BACKUP_ROOT" "$DAILY_DIR" "$WEEKLY_DIR" "$MONTHLY_DIR"
trap 'rm -f "$TEMP_FILE"' EXIT HUP INT TERM

docker exec postgres sh -c \
  'pg_dump -U "$POSTGRES_USER" -d finance -Fc --no-owner --no-acl' \
  > "$TEMP_FILE"
docker exec -i postgres pg_restore --list < "$TEMP_FILE" >/dev/null
mv "$TEMP_FILE" "$FINAL_FILE"
sha256sum "$FINAL_FILE" > "$FINAL_FILE.sha256"
chown root:root "$FINAL_FILE" "$FINAL_FILE.sha256"
chmod 640 "$FINAL_FILE" "$FINAL_FILE.sha256"

if [ "$TODAY" -eq 7 ]; then
  cp -p "$FINAL_FILE" "$WEEKLY_DIR/"
  cp -p "$FINAL_FILE.sha256" "$WEEKLY_DIR/"
fi
if [ "$DAY_OF_MONTH" = 01 ]; then
  cp -p "$FINAL_FILE" "$MONTHLY_DIR/"
  cp -p "$FINAL_FILE.sha256" "$MONTHLY_DIR/"
fi

find "$DAILY_DIR" -type f -mtime +7 -delete
find "$WEEKLY_DIR" -type f -mtime +28 -delete
find "$MONTHLY_DIR" -type f -mtime +186 -delete

echo "Backup financeiro criado e verificado: $FINAL_FILE"
