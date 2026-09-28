# 0001 — Fundação financeira

Status: aceita em 2026-09-10.

## Decisões

- O código vive neste repositório separado; nenhum arquivo do homelab é lido ou
  alterado.
- Desenvolvimento e testes usam instâncias PostgreSQL 17 próprias no Compose.
- Dinheiro usa `Decimal` na aplicação e `NUMERIC(14,2)` no banco. `float` é
  recusado nas funções financeiras.
- Instantes usam UTC. Vencimentos e datas financeiras civis usam `DATE` e são
  interpretados em `America/Campo_Grande`.
- Transações têm valor positivo e direção explícita. Receita é crédito, despesa
  é débito e transferência aceita uma perna de cada direção.
- Uma transferência própria é um par ligado por `transfer_group_id` e não entra
  nos totais de receitas e despesas consolidados.
- O saldo atual vem do snapshot confiável mais recente. O saldo inicial é usado
  para criar o primeiro snapshot, evitando descontar novamente lançamentos já
  refletidos pelo banco.
- O período do limite diário inclui hoje e termina na véspera da próxima entrada.
  Divisões são arredondadas para baixo no centavo para preservar o caráter seguro
  do limite.
- Regras explícitas de categoria usam a maior prioridade; em empate, a regra da
  conta vence a regra global.
- Eventos de auditoria guardam ação e nomes dos campos alterados, sem copiar
  descrições ou valores financeiros completos.

## Consequências

O domínio continua independente de IA e integrações. Pluggy, Telegram, Hermes,
CSV completo, proxy e implantação serão adicionados apenas nas fases próprias.
