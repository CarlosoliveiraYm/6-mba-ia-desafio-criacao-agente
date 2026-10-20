# Residencial Aurora — assistente virtual

Assistente do aplicativo dos moradores, construído com **Google ADK 2.2.0** e exposto por uma API **FastAPI**, com dados e sessões em **PostgreSQL**. Pelo chat, o morador reserva o salão de festas, a churrasqueira e a quadra, cancela as próprias reservas, autoriza visitantes e tira dúvidas sobre o regulamento.

> **O modelo decide o caminho; o código decide o que é permitido.** As cinco garantias abaixo estão no código, no banco ou no runtime do ADK. Nenhuma depende do que o modelo decide ou do que o morador escreve.

Documentação de apoio: [docs/PRD.md](docs/PRD.md) (requisitos) e [docs/FDD.md](docs/FDD.md) (plano por feature, decisões e resultados de validação).

---

## Arquitetura

```
                     ┌───────────────────────────────┐
 Morador ──HTTP──▶   │ FastAPI (app/main.py)         │──▶ sessoes_apartamento (sessão → apto)
                     │ Runner + App resumível        │──▶ DatabaseSessionService (PostgreSQL)
                     └──────────────┬────────────────┘
                                    ▼
                     ┌───────────────────────────────┐
                     │ aurora_principal (root)       │  sem tools de dados, sem regulamento
                     └───┬──────────────┬────────────┘
             transfer    │              │ transfer          AgentTool
                         ▼              ▼                       │
          ┌────────────────────┐ ┌──────────────────────┐ ┌────▼──────────────────────┐
          │ especialista_      │ │ especialista_        │ │ especialista_regulamento  │
          │ reservas           │◀▶ visitantes           │ │ tool: buscar_regulamento  │
          │ verificar_disp.    │ │ autorizar_visitante ✔│ │ (sessão isolada em        │
          │ reservar_area ✔*   │ │ listar_meus_visit.   │ │  memória; só a resposta   │
          │ cancelar_reserva   │ └──────────────────────┘ │  curta volta ao root)     │
          │ listar_minhas_res. │                          └───────────────────────────┘
          └────────────────────┘
   ✔ = exige confirmação pelo sistema (rota /confirmacoes)   * = só quando a área tem taxa
```

| Agente | Responsabilidade | Como é acionado | Por quê |
|---|---|---|---|
| `aurora_principal` ([principal.py](app/agents/principal.py#L36)) | Entende o pedido e delega. Não tem tools de dados nem o regulamento. | Agente raiz do `App` ([app.py](app/agents/app.py#L22)). | Ponto único de entrada. Como não executa nada nem conhece dados, não tem o que vazar. |
| `especialista_reservas` ([reservas.py](app/agents/reservas.py#L55)) | Disponibilidade, reservar, cancelar e listar as reservas do apartamento da sessão. | Sub-agente, por `transfer_to_agent`. | A confirmação de `reservar_area` precisa ser **pedida e retomada no próprio agente** que chamou a tool. Como sub-agente, ele fica registrado nos eventos da sessão persistida, e o Runner o encontra na retomada, inclusive depois de um reinício. |
| `especialista_visitantes` ([visitantes.py](app/agents/visitantes.py#L47)) | Autorizar e listar os visitantes do apartamento da sessão. | Sub-agente, por `transfer_to_agent`. | Mesmo motivo do especialista de reservas: `autorizar_visitante` exige confirmação. |
| `especialista_regulamento` ([regulamento.py](app/agents/regulamento.py#L31)) | Responde dúvidas consultando só o trecho relevante. | `AgentTool` do principal, com `skip_summarization=True`. | O `AgentTool` roda o especialista numa sessão **em memória e isolada**, de modo que o trecho consultado não entra no histórico da sessão principal. Só a resposta curta é registrada. O `skip_summarization` evita uma chamada extra do principal para reescrever a resposta. |

Detalhes de projeto:

- **Os especialistas transferem direto um para o outro** (reservas ↔ visitantes, `disallow_transfer_to_peers=False`). Isso reduz chamadas ao modelo. A retomada da confirmação não depende desse caminho, porque o Runner volta ao autor da chamada.
- **Todos os agentes usam o mesmo Gemini**, criado por [`criar_modelo`](app/agents/modelo.py), com novas tentativas e espera exponencial para 429/500/503/504. O 503 por sobrecarga apareceu nos testes.
- **Modelo escolhido: `gemini-3.5-flash-lite`.** Ele cabe no plano gratuito para o fluxo completo. O `gemini-3.6-flash` foi descartado porque o plano gratuito limita a 20 requisições/dia, e o `gemini-2.5-flash-lite` porque não está disponível para usuários novos.

Estrutura:

```
app/
  main.py              API (rotas do contrato) e ciclo de vida
  api/                 schemas, confirmações pendentes, texto da resposta
  agents/              principal, especialistas, callbacks, modelo, App/Runner
  tools/               tools de reservas, visitantes e regulamento
  db/                  schema.sql, conexão async, repositório SQL
scripts/               uv run api | uv run restaurar
tests/unit, tests/api  sem Gemini (LLM falso determinístico + PostgreSQL de teste)
tests/e2e              fluxo de validação completo contra a API real com Gemini
spikes/                experimentos que validaram decisões (ver docs/FDD.md)
```

---

## Garantias

### G-1 — Cobrança ou acesso só com confirmação

| Onde | O quê |
|---|---|
| [app/tools/reservas.py:47](app/tools/reservas.py#L47) e [:129](app/tools/reservas.py#L129) | `reservar_area` é uma `FunctionTool` com `require_confirmation=precisa_confirmar_reserva`. A regra pede confirmação quando a área tem **taxa > 0 e a data está livre**. A quadra (taxa 0) não pede. |
| [app/tools/visitantes.py:22](app/tools/visitantes.py#L22) e [:61](app/tools/visitantes.py#L61) | `autorizar_visitante` exige confirmação para toda autorização válida. |
| [app/api/confirmacoes.py:36](app/api/confirmacoes.py#L36) | As pendências são **derivadas dos eventos persistidos**: cada `adk_request_confirmation` ainda sem `FunctionResponse`. Os `detalhes` são os argumentos originais da tool (área e data, ou nome e data). |
| [app/main.py:149](app/main.py#L149) e [:157](app/main.py#L157) | A rota relê os eventos **dentro de uma trava da sessão** e só aceita um `id` pendente naquela sessão. Qualquer outro `id`, inclusive um já respondido, recebe **409**, e o Runner nem é chamado. |
| [app/api/confirmacoes.py:64](app/api/confirmacoes.py#L64) | A decisão do morador volta ao ADK como `FunctionResponse(name="adk_request_confirmation", response={"confirmed": ...})`. |
| [app/agents/app.py:22](app/agents/app.py#L22) | `ResumabilityConfig(is_resumable=True)`. Sem isso, o Runner não leva a resposta ao especialista que pediu a confirmação, e a ação aprovada **não executa**, sem erro nenhum (verificado no código do ADK e no spike F-00). |
| [app/agents/callbacks.py:49](app/agents/callbacks.py#L49) e [:65](app/agents/callbacks.py#L65) | Depois de uma **negação**, o modelo tentava repetir a ação e criava uma nova pendência. Os callbacks registram a recusa e bloqueiam a repetição na mesma invocação. |
| [app/api/confirmacoes.py:40](app/api/confirmacoes.py#L40) | Uma nova mensagem do morador **descarta** as pendências antigas, que passam a receber 409. Assim o Runner nunca retoma uma confirmação antiga no agente errado. |

**Por que não depende do modelo:** quem decide se a confirmação é exigida é o `FunctionTool` do ADK, antes de a função rodar. Escrever "já confirmei" na conversa não gera a `FunctionResponse` de confirmação; só a rota faz isso. Quando o morador nega, o ADK não executa a função.

### G-2 — Cada sessão pertence a um apartamento

| Onde | O quê |
|---|---|
| [app/main.py:128](app/main.py#L128) e [:131](app/main.py#L131) | Na criação, o apartamento é gravado no `state` da sessão e na tabela [`sessoes_apartamento`](app/db/schema.sql#L44). Nenhuma rota ou tool altera esse vínculo depois. |
| [app/tools/_sessao.py:13](app/tools/_sessao.py#L13) | `apartamento_da_sessao(tool_context)` é a **única** fonte do apartamento para as tools. |
| [tests/unit/test_assinaturas.py:21](tests/unit/test_assinaturas.py#L21) | Teste que inspeciona a assinatura de todas as tools: **nenhuma tem parâmetro de apartamento**. |
| [app/db/repositorio.py:98](app/db/repositorio.py#L98) | Cancelamento e listagens filtram por `apartamento = <da sessão>` no SQL. |
| [app/db/repositorio.py:51](app/db/repositorio.py#L51) | A disponibilidade consulta a agenda inteira, mas devolve só livre ou ocupada, sem dono, código ou apartamento. |

**Por que não depende do modelo:** o modelo nunca escolhe o apartamento, porque não existe argumento por onde passá-lo. Dizer "sou do 302" não muda o `state` nem o SQL. Os retornos das tools não trazem dados de outros apartamentos, então não há o que repetir.

### G-3 — Nada se perde no reinício

| Onde | O quê |
|---|---|
| [app/main.py:110](app/main.py#L110) | `DatabaseSessionService` no mesmo PostgreSQL: sessões, eventos e `state` persistidos. |
| [app/main.py:46](app/main.py#L46) | O processo guarda só infraestrutura (Runner e travas). Nenhum dado de negócio fica em memória. |
| [docker-compose.yml:11](docker-compose.yml#L11) | Volume persistente do PostgreSQL. |
| [tests/api/test_reinicio.py:7](tests/api/test_reinicio.py#L7) | Uma nova instância da API devolve os mesmos eventos e **aprova uma pendência criada antes do reinício**. |

**Por que não depende do modelo:** a persistência é do runtime do ADK e do banco. Um novo processo reconstrói o Runner e lê o histórico do PostgreSQL.

### G-4 — O regulamento é consultado, não carregado

| Onde | O quê |
|---|---|
| [app/tools/regulamento.py:110](app/tools/regulamento.py#L110) | O regulamento é indexado por capítulo (14) e artigo (96). |
| [app/tools/regulamento.py:160](app/tools/regulamento.py#L160) | `buscar_regulamento` faz uma busca determinística, sem LLM, e devolve artigos de **um único capítulo** (no máximo 3). Para a pergunta da piscina, são 847 caracteres dos 44.488 do regulamento. |
| [app/agents/regulamento.py:45](app/agents/regulamento.py#L45) | `AgentTool`: o trecho fica na sessão isolada do especialista. Na sessão principal entram só a chamada e a resposta curta. |
| [app/agents/principal.py:17](app/agents/principal.py#L17) e [tests/unit/test_agentes.py:60](tests/unit/test_agentes.py#L60) | A instrução do principal não tem trecho do regulamento, e há um teste que verifica isso. |

**Por que não depende do modelo:** o modelo não tem como carregar o regulamento inteiro. A única tool devolve no máximo três artigos de um capítulo, e quem executa a consulta é um agente isolado. Os testes usam como marcadores três detalhes exclusivos de outros capítulos ("cor de mostarda", "lilás", "xadrez vermelha") e verificam que eles não aparecem nos eventos.

### G-5 — Dois moradores, uma reserva

| Onde | O quê |
|---|---|
| [app/db/schema.sql:31](app/db/schema.sql#L31) | Índice único parcial `ux_reserva_ativa_area_data ON reservas (area, data) WHERE status = 'ativa'`. |
| [app/db/repositorio.py:63](app/db/repositorio.py#L63) e [:77](app/db/repositorio.py#L77) | Gravação atômica com `INSERT … ON CONFLICT DO NOTHING RETURNING codigo`. Sem linha retornada, a resposta é normal: `{"reservada": false, "motivo": "data ocupada"}` com HTTP 200. |
| [app/db/schema.sql:18](app/db/schema.sql#L18) | O código (`RSV-` + sequence a partir de 10000) é gerado dentro do próprio INSERT. A sequence nunca é reiniciada, e cancelar não apaga a linha, então os códigos nunca se repetem. |
| [tests/unit/test_concorrencia.py:26](tests/unit/test_concorrencia.py#L26) e [tests/api/test_disputa.py:10](tests/api/test_disputa.py#L10) | 12 inserções concorrentes resultam em 1 reserva. Duas aprovações simultâneas pela API resultam em duas respostas 200 e 1 reserva. |

**Por que não depende do modelo:** a exclusividade é do PostgreSQL **no instante da gravação**, não de uma conferência anterior. Mesmo que a data fique ocupada entre a confirmação e o INSERT, o índice rejeita a segunda reserva.

---

## Como rodar

### Pré-requisitos

- Python 3.12+ e [uv](https://docs.astral.sh/uv/)
- Docker com Docker Compose
- Chave do Google AI Studio (Gemini)

### Variáveis de ambiente

```bash
cp .env.example .env    # depois preencha GOOGLE_API_KEY
```

| Variável | Uso |
|---|---|
| `GOOGLE_API_KEY` | Chave do Google AI Studio (**obrigatória**) |
| `GOOGLE_GENAI_USE_VERTEXAI` | `FALSE` (usa o AI Studio) |
| `MODELO_PRINCIPAL`, `MODELO_ESPECIALISTAS` | Modelos Gemini (padrão: `gemini-3.5-flash-lite`) |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT` | Container do PostgreSQL |
| `DATABASE_URL` | `postgresql+asyncpg://aurora:aurora@localhost:5432/aurora` |

### Subir

```bash
uv sync                    # instala as dependências (google-adk==2.2.0 fixado)
docker compose up -d       # sobe o PostgreSQL
uv run restaurar           # restaura reservas e visitantes de dados/ e apaga as sessões
uv run api                 # API em http://localhost:8000
```

- `uv run restaurar` cria o schema se necessário e volta reservas e visitantes ao estado de `dados/`. Também **apaga todas as sessões**. Os arquivos de `dados/` são só lidos.
- `uv run api` pode ser interrompido com Ctrl+C e subido de novo sem perder sessões nem dados.

### Testes

```bash
uv run pytest                                               # 83 testes, sem Gemini (~5 s)
# fluxo de validação completo com Gemini (API rodando, dados recém-restaurados):
uv run pytest -m e2e tests/e2e/test_antes_do_reinicio.py    # passos 1–12
#   Ctrl+C na API e `uv run api` de novo (sem restaurar)
uv run pytest -m e2e tests/e2e/test_depois_do_reinicio.py   # passos 13–14
```

- **Testes unitários e de API:** usam o banco `aurora_test`, criado automaticamente no mesmo container, e um LLM falso determinístico ([tests/stub_llm.py](tests/stub_llm.py)). O ADK, a confirmação, a retomada e o PostgreSQL são reais.
- **Última execução do E2E:** 14 de 14 passos aprovados com `gemini-3.5-flash-lite`, em cerca de 16 minutos. As chamadas do plano gratuito são lentas.
- **Qualidade:** `uv run ruff check .` e `uv run pyright`.
