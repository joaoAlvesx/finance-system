from mcp.server import MCPServer

from finance_mcp.client import FinanceAPIClient

mcp = MCPServer("Finance System")


def _client() -> FinanceAPIClient:
    return FinanceAPIClient()


@mcp.tool()
def consultar_saldo(account_id: str | None = None) -> dict:
    """Consulta o saldo calculado pelo backend, opcionalmente de uma conta."""
    return _client().request("GET", "/balance", query={"account_id": account_id})


@mcp.tool()
def consultar_disponivel() -> dict:
    """Consulta disponível, reserva, déficit e limite seguro diário calculados."""
    return _client().request("GET", "/availability")


@mcp.tool()
def listar_transacoes(
    data_inicial: str,
    data_final: str,
    limite: int = 25,
    conta_id: str | None = None,
    categoria_id: str | None = None,
    busca: str | None = None,
) -> dict:
    """Lista no máximo 50 transações do período solicitado; nunca retorna o histórico inteiro."""
    return _client().request(
        "GET",
        "/transactions",
        query={
            "date_from": data_inicial,
            "date_to": data_final,
            "limit": min(max(limite, 1), 50),
            "account_id": conta_id,
            "category_id": categoria_id,
            "search": busca,
        },
    )


@mcp.tool()
def listar_contas_futuras(data_inicial: str, data_final: str, limite: int = 25) -> dict:
    """Lista no máximo 50 despesas planejadas no intervalo solicitado."""
    return _client().request(
        "GET",
        "/future-expenses",
        query={
            "date_from": data_inicial,
            "date_to": data_final,
            "limit": min(max(limite, 1), 50),
        },
    )


@mcp.tool()
def registrar_transacao_manual(
    conta_id: str,
    tipo: str,
    direcao: str,
    valor: str,
    data: str,
    descricao: str,
    confirmado: bool,
    categoria_id: str | None = None,
) -> dict:
    """Registra uma transação. Só executa depois de confirmação explícita do usuário."""
    return _client().request(
        "POST",
        "/manual-transactions",
        body={
            "account_id": conta_id,
            "type": tipo,
            "direction": direcao,
            "amount": valor,
            "transaction_date": data,
            "description": descricao,
            "category_id": categoria_id,
            "confirmed": confirmado,
        },
    )


@mcp.tool()
def alterar_categoria(
    transacao_id: str, categoria_id: str, confirmado: bool
) -> dict:
    """Altera a categoria de uma transação após confirmação explícita do usuário."""
    return _client().request(
        "POST",
        f"/transactions/{transacao_id}/category",
        body={"category_id": categoria_id, "confirmed": confirmado},
    )


@mcp.tool()
def simular_gasto(valor: str) -> dict:
    """Simula uma compra; todos os cálculos são feitos pelo backend financeiro."""
    return _client().request("POST", "/purchase-simulation", body={"amount": valor})


@mcp.tool()
def gerar_resumo_mensal(ano: int, mes: int) -> dict:
    """Gera totais determinísticos de receitas, despesas e categorias de um mês."""
    return _client().request(
        "GET", "/monthly-summary", query={"year": ano, "month": mes}
    )


@mcp.tool()
def sugerir_categoria(
    transacao_id: str,
    categoria_id: str,
    confianca: str,
    codigo_motivo: str,
) -> dict:
    """Cria uma sugestão revisável; não altera a transação automaticamente."""
    return _client().request(
        "POST",
        "/category-suggestions",
        body={
            "transaction_id": transacao_id,
            "category_id": categoria_id,
            "confidence": confianca,
            "rationale_code": codigo_motivo,
        },
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
