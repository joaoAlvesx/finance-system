# ADR 0005 — Pluggy com polling e reconciliação

## Decisão

A integração bancária usa a API da Pluggy por uma interface interna de provedor.
O navegador recebe somente um Connect Token temporário e abre o widget oficial;
`clientId`, `clientSecret` e credenciais bancárias não são gravados ou enviados ao
frontend. A conexão pessoal restringe o widget ao Conector 200, Meu Pluggy.

O worker consulta itens ativos a cada 15 minutos para detectar dados que já estejam
disponíveis na Pluggy. Esse intervalo não força a atualização da instituição. No
Meu Pluggy gratuito, a conexão original normalmente é atualizada uma vez ao dia,
e o item proxy reflete os dados disponíveis nessa origem.

Cada conta externa precisa ser vinculada explicitamente a uma conta local. A
primeira reconciliação percorre todo o histórico; as seguintes usam cursor e uma
janela de sobreposição. Uma reconciliação completa volta a percorrer o histórico.

## Idempotência e autoria

Cada transação externa é ligada à transação local pelo ID da conta e pelo ID da
Pluggy. Antes de criar uma nova transação, o worker procura o hash determinístico
já usado na importação CSV. Quando encontra uma correspondência, cria somente o
vínculo e preserva os campos do CSV. O vínculo registra se a transação é gerida
pela Pluggy; somente essas transações podem receber atualizações do provedor.

Snapshots de saldo registram origem e instante de observação. Reexecuções não
duplicam transações nem o mesmo snapshot. Regras locais explícitas de categoria
têm precedência sobre a categoria sugerida pelo provedor.

## Consentimento e falhas

Estados de credencial, consentimento revogado ou ação pendente interrompem a
sincronização e aparecem na tela de configurações para reconexão pelo widget.
Falhas transitórias usam backoff limitado e persistem apenas códigos sanitizados.
Os logs contêm contadores e identificadores técnicos, sem descrições ou valores
financeiros completos.
