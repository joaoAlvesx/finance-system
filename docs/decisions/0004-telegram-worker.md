# ADR 0004 — Alertas e comandos pelo Telegram

## Decisão

O Telegram será integrado pela Bot API diretamente em um processo
`finance-worker`, usando long polling com `getUpdates`. O bot aceita mensagens
somente do `chat_id` configurado e oferece inicialmente os comandos de leitura
`/saldo` e `/disponivel`.

Alertas de despesas usam uma outbox `notification_logs` com chave idempotente por
transação. Um checkpoint persistente evita enviar o histórico anterior à primeira
ativação. Falhas usam até três tentativas com backoff e guardam somente códigos
sanitizados. Descrições são limitadas e limpas antes de entrar na mensagem.

## Consequências

- reiniciar o worker não reenvia alertas marcados como enviados;
- o PostgreSQL continua sendo a fonte de verdade dos cálculos;
- não há webhook, porta pública, n8n ou dependência de IA;
- token e chat ID ficam apenas no ambiente do worker;
- uma falha entre o aceite da Bot API e a gravação do resultado ainda pode gerar
  repetição, pois o `sendMessage` não oferece chave de idempotência externa.
