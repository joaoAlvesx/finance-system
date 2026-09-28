"""Add the reviewed Finance routes without printing or rewriting unrelated secrets."""

import argparse
import os
import re
import stat
import tempfile
from pathlib import Path

import yaml


def atomic_write(path: Path, content: str) -> None:
    current_mode = stat.S_IMODE(path.stat().st_mode)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.chmod(temporary_name, current_mode)
        os.replace(temporary_name, path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def durable_in_place_write(path: Path, content: str) -> None:
    """Persist content without replacing a file that may be bind-mounted."""
    current_mode = stat.S_IMODE(path.stat().st_mode)
    with path.open("w", encoding="utf-8") as destination:
        destination.write(content)
        destination.flush()
        os.fsync(destination.fileno())
    os.chmod(path, current_mode)


def update_caddy(path: Path, domain: str) -> None:
    content = path.read_text(encoding="utf-8")
    if re.search(rf"(?m)^http://{re.escape(domain)}\s*\{{", content):
        return
    block = (
        f"\n\nhttp://{domain} {{\n"
        "    import protegido\n"
        "    reverse_proxy finance-web:80\n"
        "}\n"
    )
    # Caddy mounts this individual file read-only. Replacing the inode on the
    # host leaves the running container attached to the previous version.
    durable_in_place_write(path, content.rstrip() + block)


def update_authelia(path: Path, domain: str) -> None:
    content = path.read_text(encoding="utf-8")
    document = yaml.safe_load(content)
    rules = (document.get("access_control") or {}).get("rules") or []
    if any(
        domain in ([rule.get("domain")] if isinstance(rule.get("domain"), str) else rule.get("domain", []))
        for rule in rules
    ):
        return

    lines = content.splitlines(keepends=True)
    for policy_index, line in enumerate(lines):
        if not re.match(r"^\s*policy:\s*one_factor\s*(?:#.*)?$", line.rstrip("\n")):
            continue
        for domain_index in range(policy_index - 1, -1, -1):
            if re.match(
                r"^\s*(?:-\s+)?domain:\s*$", lines[domain_index].rstrip("\n")
            ):
                existing_items = [
                    candidate
                    for candidate in lines[domain_index + 1 : policy_index]
                    if re.match(r"^\s*-\s+", candidate)
                ]
                if not existing_items:
                    break
                indent = re.match(r"^(\s*)", existing_items[-1]).group(1)  # type: ignore[union-attr]
                lines.insert(policy_index, f"{indent}- {domain}\n")
                candidate = "".join(lines)
                parsed = yaml.safe_load(candidate)
                parsed_rules = (parsed.get("access_control") or {}).get("rules") or []
                if not any(
                    domain
                    in (
                        [rule.get("domain")]
                        if isinstance(rule.get("domain"), str)
                        else rule.get("domain", [])
                    )
                    for rule in parsed_rules
                ):
                    raise RuntimeError("Authelia domain insertion could not be validated")
                atomic_write(path, candidate)
                return
            if re.match(r"^\s*-\s+(?:domain|policy):", lines[domain_index]):
                break
    raise RuntimeError("Existing one_factor domain rule was not found")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--caddy", type=Path, required=True)
    parser.add_argument("--authelia", type=Path, required=True)
    parser.add_argument("--domain", default="finance.example.com")
    args = parser.parse_args()
    update_caddy(args.caddy, args.domain)
    update_authelia(args.authelia, args.domain)


if __name__ == "__main__":
    main()
