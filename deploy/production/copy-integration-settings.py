"""Copy only allowlisted integration settings without printing their values."""

import argparse
import os
import stat
import tempfile
from pathlib import Path

ALLOWED_KEYS = {
    "FINANCE_TELEGRAM_ENABLED",
    "FINANCE_TELEGRAM_BOT_TOKEN",
    "FINANCE_TELEGRAM_CHAT_ID",
    "FINANCE_TELEGRAM_API_BASE_URL",
    "FINANCE_TELEGRAM_POLL_SECONDS",
    "FINANCE_TELEGRAM_SCAN_SECONDS",
    "FINANCE_TELEGRAM_MAX_ATTEMPTS",
    "FINANCE_TELEGRAM_REQUEST_TIMEOUT_SECONDS",
    "FINANCE_PLUGGY_ENABLED",
    "FINANCE_PLUGGY_CLIENT_ID",
    "FINANCE_PLUGGY_CLIENT_SECRET",
    "FINANCE_PLUGGY_API_BASE_URL",
    "FINANCE_PLUGGY_CLIENT_USER_ID",
    "FINANCE_PLUGGY_CONNECTOR_ID",
    "FINANCE_PLUGGY_INCLUDE_SANDBOX",
    "FINANCE_PLUGGY_POLL_SECONDS",
    "FINANCE_PLUGGY_FULL_SYNC_SECONDS",
    "FINANCE_PLUGGY_WORKER_SCAN_SECONDS",
    "FINANCE_PLUGGY_REQUEST_TIMEOUT_SECONDS",
    "FINANCE_PLUGGY_MAX_ATTEMPTS",
}
REQUIRED_KEYS = {
    "FINANCE_TELEGRAM_BOT_TOKEN",
    "FINANCE_TELEGRAM_CHAT_ID",
    "FINANCE_PLUGGY_CLIENT_ID",
    "FINANCE_PLUGGY_CLIENT_SECRET",
}


def parse_env(content: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in ALLOWED_KEYS:
            values[key] = value
    return values


def value_is_present(raw_value: str) -> bool:
    return raw_value.strip().strip("'\"") != ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()

    source_values = parse_env(args.source.read_text(encoding="utf-8"))
    missing = sorted(
        key for key in REQUIRED_KEYS if not value_is_present(source_values.get(key, ""))
    )
    if missing:
        raise RuntimeError(f"Required integration settings are missing: {', '.join(missing)}")

    target_content = args.target.read_text(encoding="utf-8")
    output_lines: list[str] = []
    replaced: set[str] = set()
    for raw_line in target_content.splitlines():
        if "=" in raw_line and not raw_line.lstrip().startswith("#"):
            key = raw_line.split("=", 1)[0].strip()
            if key in source_values:
                output_lines.append(f"{key}={source_values[key]}")
                replaced.add(key)
                continue
        output_lines.append(raw_line)
    for key in sorted(source_values.keys() - replaced):
        output_lines.append(f"{key}={source_values[key]}")

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".finance-env-", dir=args.target.parent, text=True
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
            temporary.write("\n".join(output_lines).rstrip() + "\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.chmod(temporary_name, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(temporary_name, args.target)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    main()
