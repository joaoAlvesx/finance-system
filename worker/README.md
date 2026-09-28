# Worker

O `finance-worker` executa `python -m app.worker` em processo e imagem separados
da API. Ele reutiliza exclusivamente os cálculos determinísticos do backend,
mantém checkpoints e filas no PostgreSQL e não depende de n8n.

O worker fica adormecido quando `FINANCE_TELEGRAM_ENABLED=false`. Tokens e chat
IDs pertencem somente ao `.env` local ou ao mecanismo de secrets da implantação;
eles nunca devem ser adicionados a este diretório.

Na Fase 5, o mesmo processo agenda e executa sincronizações da Pluggy quando
`FINANCE_PLUGGY_ENABLED=true`. O polling lê dados disponibilizados pelo provedor,
reconcilia IDs externos de forma idempotente e aplica backoff em falhas. O worker
continua ativo se apenas uma das duas integrações estiver habilitada.
