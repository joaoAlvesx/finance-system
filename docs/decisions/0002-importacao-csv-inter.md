# 0002 — Importação CSV do Banco Inter

Status: aceita em 2026-09-15.

## Formato observado

Os três extratos fornecidos usam UTF-8 com BOM, separador `;`, cinco linhas de
preâmbulo e as colunas `Data Lançamento`, `Histórico`, `Descrição`, `Valor` e
`Saldo`. Datas usam `dd/mm/aaaa`; valores usam vírgula decimal e sinal para
distinguir crédito e débito.

Os arquivos financeiros e `informacoes.txt` permanecem fora do Git. O sistema
guarda somente metadados do arquivo, campos necessários ao preview e transações
confirmadas; o binário original não é copiado para o banco.

## Fluxo e idempotência

1. O preview valida extensão, MIME, tamanho, encoding, cabeçalhos e linhas.
2. SHA-256 impede confirmar novamente o mesmo arquivo para a mesma conta.
3. O hash de data, descrição, valor, direção e conta marca sobreposições como
   possíveis duplicidades.
4. Possíveis duplicidades são ignoradas por padrão e só entram quando o usuário
   informa explicitamente seus números de linha na confirmação.
5. A confirmação cria todas as transações em uma única transação PostgreSQL e
   registra um snapshot do saldo mais recente do arquivo.
6. Erros registram apenas códigos sanitizados; descrições e valores não são
   enviados aos logs.

Linhas iguais dentro do mesmo arquivo não são descartadas automaticamente, pois
podem representar compras legítimas repetidas. O hash integral do arquivo previne
a reimportação acidental desse conjunto.

## Categorias

Categorias e regras iniciais são determinísticas. Regras específicas, como Uber
ou Mercado, têm prioridade maior que a regra genérica de Pix. Uma correção manual
gera auditoria com os identificadores anterior e novo, permitindo desfazer a
alteração sem copiar a descrição ou o valor financeiro para a auditoria.
