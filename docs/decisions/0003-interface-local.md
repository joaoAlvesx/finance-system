# ADR 0003 — Interface local da Fase 3

## Decisão

A interface usa React, TypeScript e Vite, é compilada como arquivos estáticos e
servida por um container Nginx leve. O Nginx encaminha requisições `/api` para o
`finance-api`, evitando configurar endereços internos no bundle do navegador.

O frontend apresenta valores e recebe edições, mas não calcula saldo,
disponibilidade ou limite diário. Esses resultados vêm de endpoints
determinísticos do backend.

## Escopo

A Fase 3 oferece visão geral, transações, revisão de categorias, planejamento e
importação CSV. Telegram, Pluggy, Hermes, autenticação externa e configuração de
proxy do homelab continuam fora do escopo.

## Segurança e operação

- API e interface são vinculadas somente ao loopback no Compose local.
- O PostgreSQL de desenvolvimento não é usado como serviço externo.
- A interface não carrega fontes, scripts ou imagens de terceiros.
- O Nginx aplica cabeçalhos de conteúdo, enquadramento e política de origem.
- Valores monetários são enviados como texto decimal.
