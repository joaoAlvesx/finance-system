# Orientações do repositório

- Leia integralmente `ESPECIFICACAO_SISTEMA_FINANCEIRO.md` antes de alterar código.
- Respeite as fases e implemente somente a fase solicitada pelo usuário.
- Nunca leia `/opt/homelab/.env` nem altere serviços ou arquivos do homelab.
- Não solicite nem grave credenciais reais. Use valores fictícios em `.env.example`.
- Dinheiro usa `Decimal` no Python e `NUMERIC(14,2)` no PostgreSQL; `float` é proibido.
- Timestamps são UTC e datas civis usam `America/Campo_Grande` na apresentação.
- Preserve exclusão lógica, auditoria e idempotência de importações e sincronizações.
- IA, Hermes e integrações externas nunca calculam saldos.
- Execute `ruff` e `pytest` para mudanças no backend. Testes de migration devem usar
  exclusivamente um banco cujo nome termine em `_test`.
- Não implante nem modifique Caddy, Authelia, Cloudflare, Tailscale, AdGuard ou o
  PostgreSQL de produção sem solicitação explícita.
