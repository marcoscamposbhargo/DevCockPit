# Tasks — AI Harness MVP

Spec: `spec.md` · Plano: `plan.md` · Constituição: `docs/constitution.md` v1.0.0

Regra que vale para toda task: `pytest -q` verde e `ruff check .` limpo antes de
marcar o checkbox (**P-07**). Nenhuma task aplica migração no banco de produção
(`C:/Users/User/DevCockpit/data/devcockpit.db`) — isso é exclusividade da T-14,
para o painel do dia a dia não ficar quebrado no meio do ciclo.

## Onda 1 — sem dependências

### T-01 — Registro declarativo de providers e modelos
- [x] Cumpre: REQ-01, REQ-02, REQ-03, REQ-04
- Arquivos: `app/services/ai/registry.py`, `configs/ai.example.yml`,
  `app/core/config.py`, `tests/unit/test_ai_registry.py`
- Detalhe: `AiConfig` no molde de `RootsConfig` (`app/core/config.py:189`) —
  `load(path)` + fábrica `@lru_cache`. Arquivo ausente devolve config vazia, não
  erro. Carga recusa qualquer campo cujo valor pareça uma chave de API. Settings
  ganha `ai_config_file` e `ai_max_attempts`. `.gitignore` recebe
  `configs/ai.yml`.
- Pronto quando: arquivo ausente não quebra nada e a suíte atual passa inteira;
  YAML com `enabled: false` some do registro; YAML com `api_key:` literal
  levanta erro nomeando o arquivo; consulta por capacidade devolve os modelos na
  ordem de provider declarada.
- Depende de: —

### T-02 — Provider genérico para APIs compatíveis com OpenAI
- [x] Cumpre: REQ-05
- Arquivos: `app/services/ai/providers.py`,
  `tests/unit/test_ai_provider_wire.py`
- Detalhe: `name` passa a atributo de instância com padrão de classe, para o
  mesmo cliente servir DeepSeek e Kimi com identidades distintas nos registros.
  `build_provider` mantém a assinatura e o caminho do `.env` intactos. Se a
  contagem de tokens no stream ou o formato de erro de algum dos dois divergir,
  a diferença vira subclasse pequena — nunca cópia do provider.
- Pronto quando: servidor de imitação de DeepSeek e de Kimi exercita `stream` e
  `complete` em cada um, com texto acumulado e tokens conferidos; um teste prova
  que os dois usam a mesma classe diferindo só por configuração; os testes
  atuais de provider seguem passando sem alteração.
- Depende de: —

### T-03 — Task Classifier por regra
- [x] Cumpre: REQ-06
- Arquivos: `app/services/ai/classifier.py`,
  `tests/unit/test_ai_classifier.py`
- Detalhe: só regra — palavra-chave, tamanho da pergunta, presença de caminho de
  arquivo, marca explícita de privacidade. Nenhuma chamada a modelo.
- Pronto quando: tabela de casos cobre os nove `task_type` com ao menos um
  exemplo cada; `complexity` fica em 0–100; classificar 100 perguntas mede menos
  de 50 ms por pergunta.
- Depende de: —

### T-04 — Tabela `ai_run` e migração 010
- [x] Cumpre: REQ-10 (schema)
- Arquivos: `app/models/ai_run.py`, `app/models/__init__.py`,
  `migrations/versions/010_ai_run.py`, `app/repositories/ai_repository.py`
- Detalhe: colunas conforme `plan.md`. `estimated_cost` e `price_date`
  anuláveis por **P-02**. Sem coluna de prompt ou resposta. Repositório com
  gravar tentativa, ler por `correlation_id` e agregar período.
- Pronto quando: `alembic upgrade head` e `downgrade` funcionam **em banco
  temporário próprio**, nunca no de produção; teste grava três tentativas do
  mesmo `correlation_id` e lê de volta na ordem.
- Depende de: —

### T-05 — `.project-ai/` no Context Engine
- [x] Cumpre: REQ-15
- Arquivos: `app/services/ai/context_engine.py`,
  `tests/unit/test_ai_context_project_ai.py`
- Detalhe: os sete arquivos entram como fonte de documento, sujeitos à mesma
  seleção por relevância e ao mesmo teto de tokens. Não seguir link simbólico
  que aponte para fora do projeto.
- Pronto quando: projeto com `.project-ai/ARCHITECTURE.md` tem o conteúdo no
  contexto; projeto sem a pasta produz contexto idêntico ao de antes da
  mudança; link simbólico para fora é ignorado.
- Depende de: —

## Onda 2

### T-06 — Model Router
- [x] Cumpre: REQ-07, REQ-08
- Arquivos: `app/services/ai/model_router.py`, `tests/unit/test_ai_router.py`
- Detalhe: precedência do REQ-07 — `privacy: local` primeiro e sem exceção;
  depois complexidade; depois padrão. Limiares vêm do YAML, não de constante.
  Devolve lista ordenada de candidatos, que o runner consome de cima para baixo.
- Pronto quando: complexidade 10, 50 e 90 escolhem o esperado; `privacy: local`
  com complexidade 95 escolhe local; sem modelo local habilitado a pergunta é
  **recusada** e o teste falha se a escolha cair em provider `type: cloud`;
  escolha manual vence e marca `manual`; capacidade ausente cai no padrão sem
  levantar.
- Depende de: T-01, T-03

### T-07 — Custo estimado a partir da tabela datada
- [x] Cumpre: REQ-11
- Arquivos: `app/services/ai/custo.py`, `tests/unit/test_ai_custo.py`
- Correção de rota (2026-09-03): a versão original desta task listava
  `runner.py`, que a T-09 cria. Duas tasks escrevendo o mesmo arquivo é
  colisão; o cálculo vira módulo próprio e a T-09 o consome.
- Detalhe: preço por milhão de tokens declarado por modelo, com a data em que
  foi anotado. Modelo sem preço grava `null`, nunca `0`.
- Pronto quando: modelo com preço gera valor coerente com tokens × preço e
  carrega `price_date`; modelo sem preço gera `null`; nenhum caminho produz `0`
  por ausência de dado.
- Depende de: T-01, T-04

### T-08 — Rotas de providers, modelos e saúde
- [x] Cumpre: REQ-13
- Arquivos: `app/api/routes/ai.py`, `app/schemas/ai.py`,
  `tests/integration/test_ai_harness_api.py`
- Detalhe: `GET /api/ai/providers`, `GET /api/ai/models`, `GET /api/ai/health`.
  Nenhuma delas devolve valor de chave, nem mascarado.
- Pronto quando: com um provider apontando para porta fechada, `/health`
  devolve 200 marcando um disponível e o outro indisponível com motivo;
  varredura da resposta procurando a chave de teste não encontra nada.
- Depende de: T-01

## Onda 3

### T-09 — Runner com cadeia de fallback
- [x] Cumpre: REQ-09, REQ-10 (gravação)
- Arquivos: `app/services/ai/runner.py`, `tests/unit/test_ai_fallback.py`
- Detalhe: erro repetível é **lista explícita** (timeout, conexão, 5xx, 429,
  modelo não encontrado); 401, 403, orçamento estourado e recusa por política
  não repetem; erro desconhecido **não** repete. Nenhum provider tentado duas
  vezes. As tentativas são acumuladas em memória e gravadas em transação curta
  **depois** do stream fechar — este é o ponto que já causou `database is
  locked` na Fase 3 (`fbabea1`).
- Pronto quando: `FakeProvider` roteirizado timeout → erro → sucesso devolve
  resposta com três linhas gravadas e a última em `ok`; chave inválida não gera
  segunda tentativa; cadeia esgotada dá erro único com contagem e motivo da
  última; teste de concorrência prova que outra escrita do painel funciona
  durante um stream em curso; varredura das linhas não encontra trecho do
  prompt.
- Depende de: T-01, T-04, T-06

### T-10 — Rota de consumo
- [x] Cumpre: REQ-12 (backend)
- Arquivos: `app/api/routes/ai.py`, `app/schemas/ai.py`,
  `app/repositories/ai_repository.py`,
  `tests/integration/test_ai_harness_api.py`
- Detalhe: `GET /api/ai/usage` com chamadas, tokens, divisão local × cloud,
  custo com a data da tabela, latência média, falhas e fallbacks acionados.
- Pronto quando: todos os campos vêm preenchidos; com banco vazio os
  indicadores vêm como não medidos e o teste falha se algum vier `0` por
  ausência de dado.
- Depende de: T-04, T-07

### T-11 — Estado dos providers em Configurações
- [x] Cumpre: REQ-14
- Arquivos: `frontend/js/pages/settings.js`, `tests/frontend/`
- Detalhe: conectado, não configurado, desligado ou indisponível. O valor da
  chave nunca aparece, nem parcialmente mascarado.
- Pronto quando: o estado exibido bate com o do registry; varredura do HTML
  servido procurando a chave de teste não encontra nada.
- Depende de: T-08

## Onda 4

### T-12 — Ligar o chat ao runner
- [x] Cumpre: integração de REQ-06 a REQ-11 no caminho real
- Arquivos: `app/services/ai/chat_service.py`, `tests/unit/test_ai_chat.py`
- Detalhe: `chat_service` chama `runner.executar(...)` no lugar de
  `build_provider(...)`. `_exigir_orcamento` continua onde está e continua
  interrompendo **antes** da cadeia — orçamento não é falha de provider.
- Pronto quando: os testes atuais de chat passam sem alteração; uma pergunta com
  fallback grava as tentativas e devolve a resposta; teto estourado interrompe
  sem tentar o próximo provider.
- Depende de: T-09

### T-13 — Tela de consumo
- [x] Cumpre: REQ-12 (tela)
- Arquivos: `frontend/js/pages/ai-usage.js`, `frontend/js/router.js`,
  `tests/frontend/`
- Detalhe: indicador sem dado aparece em cinza como "não medido", com o que
  falta para poder ser medido — nunca zero (**P-02**). Onde o custo aparece, a
  data da tabela aparece junto.
- Pronto quando: a tela abre com banco vazio sem mostrar nenhum zero falso; com
  dados, mostra os campos da rota.
- Depende de: T-10

### T-12.1 — Ligar `ask_quick` ao runner
- [x] Cumpre: REQ-09, REQ-10 no segundo caminho de chat
- Arquivos: `app/services/ai/chat_service.py`, `tests/unit/test_ai_chat.py`
- Origem: a T-12 ligou só `ask()` (histórico e contexto de projeto), porque era
  o alvo explícito dos critérios de aceite. `ask_quick()` — único chamador real:
  `POST /api/ai/chat` em `app/api/routes/ai.py:480` — ficou fora, sem fallback e
  sem gravar `ai_run`. `write_summary()` não tem chamador na base hoje; decisão
  do usuário foi fechar só `ask_quick`.
- Detalhe: mesmo padrão da T-12 — `self.provider` injetado continua vencendo
  sempre, para não alterar o comportamento dos testes existentes; sem ele,
  `classificar()` + `escolher()` decidem; `Decisao` recusada vira
  `PerguntaRecusada` sem tentar provider; `Decisao` com candidatos vai pelo
  `Runner`; `Decisao` sem candidatos (registro vazio, REQ-04) cai no
  `_exigir_provedor(perfil)` de sempre, sem `Runner` e sem gravar `ai_run`.
- Pronto quando: pergunta rápida com fallback grava as tentativas em `ai_run`;
  registro vazio continua indo pelo `.env` sem `Runner`; os testes atuais de
  `ask_quick` continuam passando sem alteração de expectativa.
- Depende de: T-09, T-12

## Onda 5 — precisa da máquina e das chaves do usuário

### T-14 — Configuração real, migração aplicada e executável reconstruído
- [ ] Cumpre: fecha REQ-05 (verificação ao vivo) e REQ-11 (preços reais)
- Arquivos: `configs/ai.yml` (não versionado), `.env` (não versionado),
  `.env.example`
- Detalhe, nesta ordem: escrever `configs/ai.yml` com os identificadores e
  preços que o usuário confirmar, com a data; pôr as duas chaves no `.env`;
  aplicar a migração 010 no banco de produção; **parar o processo**
  (`Get-Process DevCockpit | Stop-Process -Force`), reconstruir
  (`python -m PyInstaller devcockpit.spec --noconfirm`) e reinstalar trocando
  `_internal` e `DevCockpit.exe`; conferir que o processo não voltou sozinho.
- Pronto quando: pergunta real responde pelo DeepSeek e pelo Kimi com custo na
  tela; Ollama parado + pergunta `privacy: local` dá recusa explicada sem ir
  para a nuvem; chave inválida de propósito não gera segunda tentativa; o painel
  instalado abre sem erro de revisão.
- Depende de: T-01 a T-13

## Cobertura dos requisitos

| REQ | Task |
|---|---|
| REQ-01, 02, 03, 04 | T-01 |
| REQ-05 | T-02, T-14 |
| REQ-06 | T-03 |
| REQ-07, 08 | T-06 |
| REQ-09 | T-09 |
| REQ-10 | T-04 (schema), T-09 (gravação) |
| REQ-11 | T-07, T-14 |
| REQ-12 | T-10, T-13 |
| REQ-13 | T-08 |
| REQ-14 | T-11 |
| REQ-15 | T-05 |

Nenhum REQ ficou sem task.
