import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "merge-homelab-config.py"


def load_module():
    spec = importlib.util.spec_from_file_location("merge_homelab_config", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_update_caddy_preserves_inode_for_bind_mount(tmp_path: Path) -> None:
    module = load_module()
    caddyfile = tmp_path / "Caddyfile"
    caddyfile.write_text("http://example.test {\n    respond 200\n}\n", encoding="utf-8")
    original_inode = caddyfile.stat().st_ino

    module.update_caddy(caddyfile, "finance.example.com")

    assert caddyfile.stat().st_ino == original_inode
    assert "http://finance.example.com" in caddyfile.read_text(encoding="utf-8")


def test_update_caddy_is_idempotent(tmp_path: Path) -> None:
    module = load_module()
    caddyfile = tmp_path / "Caddyfile"
    caddyfile.write_text("http://example.test {\n    respond 200\n}\n", encoding="utf-8")

    module.update_caddy(caddyfile, "finance.example.com")
    first_update = caddyfile.read_text(encoding="utf-8")
    module.update_caddy(caddyfile, "finance.example.com")

    assert caddyfile.read_text(encoding="utf-8") == first_update
