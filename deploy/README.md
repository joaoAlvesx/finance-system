# Implantação

Os exemplos revisáveis da Fase 7 ficam em `production/`. Eles cobrem Compose de
produção, banco exclusivo, Caddy, Authelia, backup, restauração e rollback. O
Uptime Kuma foi retirado do escopo por decisão do usuário.

Nenhum exemplo lê `/opt/homelab/.env` ou deve ser aplicado sem backup e janela de
manutenção.
