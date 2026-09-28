# Produção no homelab — Fase 7

Estes arquivos são revisáveis e não devem ser aplicados sem backup e janela de
manutenção. Eles nunca leem `/opt/homelab/.env`.

## Decisões

- hostname de exemplo: `finance.example.com`;
- Authelia: `one_factor`, igual aos demais serviços protegidos;
- banco e usuário exclusivos: `finance` e `finance_app`;
- PostgreSQL existente, sem porta publicada;
- rede Docker externa: `homelab`;
- API para o Hermes: `http://127.0.0.1:18000`;
- backups: `/backup/finance`, 7 diários, 4 semanais e 6 mensais;
- Telegram e Pluggy permanecem ativos após o corte;
- Uptime Kuma não faz parte desta implantação.

## Preparação sem alteração de produção

1. Construir e testar as imagens `0.6.0` no repositório.
2. Criar `/opt/homelab/finance` com proprietário `root:root` e modo 750.
3. Copiar o Compose, scripts e unidades revisados para esse diretório.
4. Criar `finance.env` com modo 600 e uma senha hexadecimal aleatória.
5. Executar `copy-integration-settings.sh`, que copia somente a lista permitida
   de variáveis Telegram/Pluggy do `.env` local. O script não imprime valores e
   nunca copia banco, portas, CORS ou ambiente de desenvolvimento.
6. Validar o Compose com `docker compose config --quiet`.

## Corte controlado

1. Parar apenas o worker local para congelar sincronizações.
2. Criar um dump do banco local e validar seu catálogo com `pg_restore --list`.
3. Criar `finance` e `finance_app` pelo script fornecido.
4. Restaurar o dump com `--no-owner --no-acl`.
5. Iniciar `api` e `web` de produção; validar healthcheck e contagens.
6. Iniciar o worker de produção e confirmar Telegram/Pluggy.
7. Atualizar o MCP do Hermes para `http://127.0.0.1:18000`.
8. Acrescentar o bloco do Caddy e o domínio à regra `one_factor` do Authelia.
9. Validar as configurações antes de recarregar o Caddy ou reiniciar o
   Authelia. O merge preserva o inode do Caddyfile porque ele é montado como um
   arquivo individual no contêiner.
10. Criar no painel do Cloudflare Tunnel o hostname público
    `finance.example.com` apontando para `http://localhost:8080`.
11. Validar acesso autenticado e as ferramentas do Hermes.
12. Instalar e testar o timer de backup.

## Rollback

Se qualquer validação falhar, parar a pilha `finance-production`, restaurar os
backups dos arquivos Caddy/Authelia, manter a rota Cloudflare desabilitada e
reiniciar o Compose local anterior. O dump de origem nunca é alterado.

Não remover o banco local nem volumes durante o primeiro ciclo de produção.
