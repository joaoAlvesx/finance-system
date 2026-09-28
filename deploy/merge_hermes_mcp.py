"""Merge the Finance MCP server into Hermes config without printing secrets."""

import argparse
import os
import shutil
import stat
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import yaml


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--token", required=True)
    parser.add_argument("--command", required=True)
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    config_path: Path = args.config
    if config_path.exists():
        document = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(document, dict):
            raise TypeError("Hermes config root must be a mapping")
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        backup_path = config_path.with_name(f"{config_path.name}.before-finance-{timestamp}")
        shutil.copy2(config_path, backup_path)
        backup_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    else:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        document = {}

    servers = document.setdefault("mcp_servers", {})
    if not isinstance(servers, dict):
        raise TypeError("Hermes mcp_servers must be a mapping")
    servers["finance"] = {
        "command": args.command,
        "env": {
            "FINANCE_API_URL": args.api_url,
            "FINANCE_API_TOKEN": args.token,
        },
        "tools": {
            "include": [
                "consultar_saldo",
                "consultar_disponivel",
                "listar_transacoes",
                "listar_contas_futuras",
                "simular_gasto",
                "gerar_resumo_mensal",
                "sugerir_categoria",
            ]
        },
    }

    rendered = yaml.safe_dump(document, sort_keys=False, allow_unicode=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".config-finance-", dir=config_path.parent, text=True
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
            temporary.write(rendered)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.chmod(temporary_name, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(temporary_name, config_path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    main()
