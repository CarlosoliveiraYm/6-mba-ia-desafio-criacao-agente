# CLAUDE.md — Residencial Aurora

Assistente virtual de condomínio com Google ADK + FastAPI + PostgreSQL.

- Requisitos: [docs/PRD.md](docs/PRD.md)
- Plano e design por feature: [docs/FDD.md](docs/FDD.md)

> Filosofia: **o modelo decide o caminho; o código decide o que é permitido.**
> Nenhuma regra crítica (G-1..G-5) pode depender de prompt.

## Comandos

```bash
docker compose up -d          # PostgreSQL
uv sync                       # dependências
uv run restaurar              # restaura dados/ e apaga sessões
uv run api                    # API em http://localhost:8000
uv run pytest                 # unitários + API (sem Gemini)
uv run pytest -m e2e          # fluxo completo com Gemini (API rodando)
uv run ruff check . && uv run ruff format --check .
uv run pyright
```

## Regras invioláveis

1. **Nunca alterar `dados/`.** Os arquivos só são lidos. Confira com `git diff --stat dados/` (precisa vir vazio).
2. **Nunca versionar segredos.** `.env` fica fora do Git, e `.env.example` só leva nomes e valores não secretos.
3. **Nenhuma tool recebe `apartamento` como parâmetro.** O apartamento vem só de `apartamento_da_sessao(tool_context)` (`app/tools/_sessao.py`).
4. **Retorno de tool nunca contém dados de outro apartamento**: nem código de reserva, nem número de apartamento, nem nome de visitante.
5. **Toda ação de cobrança ou de acesso** é uma `FunctionTool` com `require_confirmation`. Nunca confirmar pela conversa.
6. **A exclusividade de reserva é do banco** (índice único parcial + `INSERT ... ON CONFLICT DO NOTHING`). Nunca implementar como `SELECT` seguido de `INSERT`.
7. **O regulamento nunca entra na instrução do agente principal** nem volta inteiro de uma tool. Só sai o trecho de um único capítulo.
8. **Nenhum estado relevante em memória.** Tudo o que precisa sobreviver ao reinício fica no PostgreSQL.
9. O `App` do ADK sempre usa `ResumabilityConfig(is_resumable=True)`.
10. A versão do `google-adk` é fixada com `==`. Atualizar só com um motivo registrado no FDD.

## Convenções de código

- **Idioma:** identificadores, módulos, comentários e docstrings em **pt-BR**, sem acentos nos identificadores (`reservar_area`, `apartamento_da_sessao`). Os termos técnicos consagrados ficam no original (`session_id`, `runner`, `engine`).
- Os nomes seguem o FDD (seção 8). Se precisar divergir, atualize o FDD no mesmo commit.
- **Docstrings de tools são prompt**: o Gemini as lê para decidir a chamada. Devem ser curtas, dizer o formato das datas (`AAAA-MM-DD`), listar os valores válidos (`salao-de-festas | churrasqueira | quadra`) e não citar regras que o código já garante.
- Python 3.12+, com type hints em todas as funções públicas. Para dados internos, `dataclass(frozen=True)`; nos contratos da API, `pydantic.BaseModel`.
- Async de ponta a ponta: SQLAlchemy 2 async + asyncpg. Nada de I/O bloqueante dentro de rotas ou de tools.
- **SQL sempre parametrizado** (`text()` com bind params). Nunca montar SQL com f-string.
- Tools devolvem `dict` simples. Erro de entrada (área ou data inválida) vira `{"erro": "..."}`, sem exceção.
- A API nunca devolve `5xx` para uma entrada válida. Os únicos códigos de erro previstos são `404` e `409` (além do `422` de corpo inválido do FastAPI).
- Logs com `logging` (logger `aurora.<modulo>`), nunca `print`. Os logs não podem conter a `GOOGLE_API_KEY`.

## Qualidade

- `ruff` (lint + format, `line-length = 100`) e `pyright` (modo `basic`) precisam passar antes de cada commit.
- Cada feature F-xx só está pronta quando cumpre a definição de pronto do FDD (seção 9.1): testes da feature verdes, CA verificados e matriz de rastreabilidade atualizada.
- Testes unitários e de API **não chamam o Gemini**. Usam o banco `aurora_test` e o LLM falso (`tests/stub_llm.py`).
- Toda mudança que toque G-1..G-5 precisa de um teste que falharia sem ela.

## Git

- Os commits vão **direto na `main`**. Cada commit é pequeno e deixa os testes verdes.
- Mensagens em **Conventional Commits com o ID da feature**: tipo em inglês, descrição em pt-BR.
  - `feat(reservas): F-09 grava reserva atômica com índice único`
  - `test(confirmacoes): F-24 cobre reenvio com 409`
  - `docs(fdd): registra decisão do spike F-00`
  - `chore(deps): F-01 fixa google-adk==2.2.0`
- Escopos: `infra`, `db`, `reservas`, `visitantes`, `regulamento`, `agentes`, `api`, `confirmacoes`, `testes`, `docs`, `deps`.
- Não commitar `.env`, `.venv/`, `.adk/`, `*.db` nem `__pycache__/`.

## Fluxo de trabalho por feature (FDD)

1. Reler a feature no FDD (walkthrough) e confirmar dependências.
2. Ajustar o design no FDD se algo mudou.
3. Implementar + testes.
4. `ruff`, `pyright`, `pytest` verdes → `/code-review`.
5. Commit `tipo(escopo): F-xx ...` e marcar o progresso no FDD (seção 9.3).
