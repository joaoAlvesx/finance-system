# ADR 0006 — API com escopos para o Hermes

## Estado

Aceita na Fase 6.

## Decisão

O Hermes executa sob seu usuário Linux isolado e usa um adaptador MCP por
entrada/saída padrão. O adaptador chama apenas a Finance API no loopback. Ele não
recebe acesso ao PostgreSQL, Docker, sudo ou ao diretório do usuário da aplicação.

Tokens de serviço são aleatórios, mostrados apenas na criação e persistidos como
SHA-256. Cada token declara escopos independentes:

- `finance:read`: saldo, disponível, transações limitadas, contas futuras e resumo;
- `finance:simulate`: simulação de compra;
- `finance:suggest`: proposta de categoria sujeita a revisão;
- `finance:write`: criação manual e alteração de categoria, ambas confirmadas.

O token padrão do Hermes omite `finance:write`. A inclusão de escrita precisa ser
explícita na rotação do token e na lista de ferramentas do Hermes.

Cada chamada autenticada grava nome da ferramenta, resultado, identificador do
token, instante e correlation ID. O registro não contém corpo da requisição,
resposta, valor financeiro ou descrição bancária. Alterações financeiras também
geram `AuditEvent` com ator de serviço. Aceitação e rejeição de sugestões geram
auditoria como ação do usuário.

## Limites de dados

Listas exigem período, aceitam no máximo 366 dias e retornam até 50 registros.
Resumos e projeções retornam agregados. Todos os saldos, limites e simulações são
calculados pela Finance API com `Decimal`; o Hermes apenas apresenta o resultado.

Perguntas e descrições bancárias são dados não confiáveis. O adaptador não as
executa como código, não constrói SQL e não inclui segredos em mensagens de erro.
O frontend usa a renderização escapada do React.

## Operação

O frontend continua funcionando quando o Hermes estiver parado. O MCP pode ser
instalado como uma cópia independente em `/home/hermes/.local/share/finance-mcp`.
O arquivo `~hermes/.hermes/config.yaml` deve pertencer a `hermes`, ter modo 600 e
conter a URL de loopback e o token. A indisponibilidade de internet ou do modelo
de IA não afeta o ledger, sincronizações, alertas ou cálculos locais.
