# Rodar o Finance System em outro computador

Este guia usa o `docker-compose.yml` da raiz para iniciar uma instalação local e
independente. O banco criado no seu computador começa vazio. Nenhum dado
financeiro do computador de quem enviou o projeto acompanha estes arquivos.

## Arquivos que devem ser enviados

Monte um ZIP com esta estrutura, mantendo os nomes e as posições:

```text
finance-system/
├── docker-compose.yml
├── backend/
├── frontend/
└── instruçoes/
    ├── .env.example
    └── README.md
```

Envie o conteúdo de `backend/` e `frontend/`, inclusive os `Dockerfile`,
`backend/alembic/`, `backend/pyproject.toml`, `frontend/package.json` e
`frontend/package-lock.json`. O `docker-compose.yml` precisa ficar na mesma
pasta dessas três pastas. O diretório `deploy/` e o Compose de produção não são
necessários para esta instalação.

Antes de compactar, confira que o ZIP **não contém** `.env`, extratos ou CSVs
particulares, `informacoes.txt`, bancos ou dumps, `.local/`, `.git/`, `.venv/`,
`node_modules/`, `dist/` ou arquivos com tokens e senhas reais. O arquivo
`instruçoes/.env.example` contém apenas valores fictícios e deve ser enviado.

## Pré-requisito

Instale e inicie o Docker Desktop (Windows/macOS) ou Docker Engine com o plugin
Docker Compose (Linux). Confirme que `docker compose version` funciona no
terminal. Na primeira execução, o Docker precisará baixar as imagens base e as
dependências para construir a aplicação.

## Iniciar

1. Extraia o ZIP e abra um terminal na pasta `finance-system/`, onde está
   `docker-compose.yml`.
2. Crie seu `.env` local a partir do exemplo:

   macOS/Linux:

   ```bash
   cp instruçoes/.env.example .env
   ```

   Windows PowerShell:

   ```powershell
   Copy-Item 'instruçoes/.env.example' '.env'
   ```

3. Antes da primeira inicialização, altere `POSTGRES_PASSWORD` no seu `.env` para
   uma senha local própria. Use letras, números e `_`, sem espaços, pois o Compose
   monta a URL do banco com esse valor. Mantenha o `.env` apenas no seu computador.
4. Construa e inicie os serviços:

   ```bash
   docker compose up --build -d
   docker compose ps
   ```

5. Abra <http://127.0.0.1:5173> no navegador. A API pode ser verificada em
   <http://127.0.0.1:8000/api/v1/health>.

Se alguma dessas portas já estiver em uso, altere `FINANCE_WEB_PORT` ou
`FINANCE_API_PORT` no seu `.env` antes de iniciar. Se a porta 5432 estiver em
uso, altere `POSTGRES_PORT`. A interface será aberta na porta escolhida em
`FINANCE_WEB_PORT`.

## Parar e voltar a usar

Na pasta do projeto:

```bash
docker compose down
```

Esse comando mantém o volume do PostgreSQL com os dados desta instalação. Para
iniciar novamente, execute `docker compose up -d`. **Não use**
`docker compose down -v` se quiser preservar os dados: `-v` apaga o volume do
banco.

As portas deste Compose estão ligadas a `127.0.0.1`: a instalação é acessível
somente no próprio computador. Ela não configura acesso pela internet. Telegram
e Pluggy permanecem desativados no exemplo.
