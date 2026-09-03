# Plano — AI Harness MVP

Spec: `docs/specs/ai-harness-mvp/spec.md`
Constituição: `docs/constitution.md` v1.0.0
Escrito em 2026-09-03

## Forma geral

Nada de camada nova. O Cockpit AI já tem a divisão certa — provider, contexto,
orquestrador, especialistas, ações — e o que falta encaixa como três peças novas
no mesmo diretório, mais uma tabela e um arquivo de configuração:

```
configs/ai.yml            (novo, opcional)   registro declarativo
       │
       ▼
app/services/ai/registry.py   (novo)   providers e modelos habilitados
       │
       ├──► classifier.py     (novo)   pergunta -> task_type, complexity, privacy
       ├──► model_router.py   (novo)   classificação -> candidatos, em ordem
       └──► runner.py         (novo)   tenta a cadeia, grava ai_run, devolve
                    │
                    ▼
            providers.py      (existe, estendido)
```

`chat_service.py` deixa de chamar `build_provider` direto e passa a chamar o
`runner`. É a única mudança de fluxo; o resto do serviço não muda.

## Arquivos

### Criados

| Arquivo | Papel |
|---|---|
| `configs/ai.example.yml` | Formato documentado do registro: providers, modelos, capacidades, tabela de preço com data, cadeia de fallback, limiares do router. Versionado. |
| `configs/ai.yml` | O registro real desta máquina. **Não versionado** (entra no `.gitignore` junto de `roots.yml`), porque nomeia variáveis de ambiente e reflete o que está instalado aqui. |
| `app/services/ai/registry.py` | `AiConfig` com `load(path)` e `@lru_cache get_ai_config()`. Expõe `providers_habilitados()`, `modelos_por_capacidade(cap)`, `preco(modelo)`, `cadeia_fallback()`. |
| `app/services/ai/classifier.py` | `classificar(pergunta, estado) -> Classificacao`. Só regra: palavra-chave, tamanho, presença de caminho de arquivo, marca explícita de privacidade. |
| `app/services/ai/model_router.py` | `escolher(classificacao, manual) -> list[Candidato]`. Devolve a lista já ordenada; o runner consome de cima para baixo. |
| `app/services/ai/runner.py` | Executa a cadeia, mede latência, decide o que é erro repetível, grava uma linha por tentativa, para no primeiro sucesso. |
| `app/models/ai_run.py` | Tabela `ai_run`. |
| `migrations/versions/010_ai_run.py` | Migração da tabela. |
| `frontend/js/pages/ai-usage.js` | Tela de consumo (REQ-12). |
| `tests/unit/test_ai_registry.py` | REQ-01 a REQ-04. |
| `tests/unit/test_ai_classifier.py` | REQ-06. |
| `tests/unit/test_ai_router.py` | REQ-07, REQ-08. |
| `tests/unit/test_ai_fallback.py` | REQ-09, REQ-10. |
| `tests/unit/test_ai_custo.py` | REQ-11. |
| `tests/integration/test_ai_harness_api.py` | REQ-12, REQ-13, REQ-14. |

### Alterados

| Arquivo | O que muda |
|---|---|
| `app/services/ai/providers.py` | `name` vira atributo de instância com padrão de classe, para o mesmo cliente servir DeepSeek e Kimi com identidades distintas nos registros. `build_provider` ganha um caminho que monta a partir do registry, mantendo o caminho do `.env` intacto (REQ-04). |
| `app/services/ai/chat_service.py` | Chama `runner.executar(...)` no lugar de `build_provider(...)`. `_exigir_orcamento` continua onde está e continua interrompendo antes da cadeia. |
| `app/services/ai/context_engine.py` | `DOCUMENTOS` ganha os sete arquivos de `.project-ai/`; `_documentos` passa a olhar a subpasta, sem seguir link simbólico. |
| `app/core/config.py` | `ai_config_file: Path = Path("./configs/ai.yml")` e `ai_max_attempts: int = 3`. Nada mais. |
| `app/repositories/ai_repository.py` | Repositório de `ai_run`: gravar tentativa, ler por `correlation_id`, agregar período para a tela de consumo. |
| `app/api/routes/ai.py` | `GET /api/ai/providers`, `GET /api/ai/models`, `GET /api/ai/health`, `GET /api/ai/usage`. |
| `app/schemas/` | Schemas de saída das quatro rotas. |
| `frontend/js/pages/settings.js` | Bloco "AI Providers" com o estado de cada um (REQ-14). |
| `frontend/js/router.js` | Rota da tela de consumo. |
| `.env.example` | `DEVCOCKPIT_AI_KEY_DEEPSEEK`, `DEVCOCKPIT_AI_KEY_MOONSHOT`, `DEVCOCKPIT_AI_CONFIG_FILE`, `DEVCOCKPIT_AI_MAX_ATTEMPTS`, com o aviso de que o valor da chave nunca sai do ambiente. |
| `.gitignore` | `configs/ai.yml`. |

## Decisões técnicas

**O registro segue o padrão de `RootsConfig`, não de `BaseSettings`.**
Classe simples com `load(path)` e fábrica `@lru_cache`, exatamente como
`app/core/config.py:189`. Descartado: Pydantic Settings aninhado — mistura
ambiente com arquivo num objeto só e foge do padrão que o projeto já tem para
configuração vinda de YAML.

**Arquivo ausente devolve config vazia, não erro.** `RootsConfig.load` já faz
isso e é o comportamento que REQ-04 exige. Descartado: exigir o arquivo — mataria
a instalação existente na primeira atualização.

**O provider genérico é o `OpenAIProvider` de hoje, com `name` de instância.**
Ele já é um cliente `/v1/chat/completions` completo, com `stream_options.
include_usage` para contar tokens no stream. DeepSeek e Kimi expõem esse
formato. Descartado: uma classe por fornecedor — seriam três cópias do mesmo
código divergindo com o tempo. **A confirmar na implementação:** se a contagem de
tokens no stream ou o formato de erro divergirem, a diferença vira subclasse
pequena, não cópia.

**O classificador é regra pura e não chama modelo.** REQ-06 exige menos de 50 ms.
Descartado: classificar com LLM — medido em 3 a 26 s nesta máquina na Fase 3, e
foi por isso que o modelo saiu do desempate do orquestrador.

**A cadeia de tentativas vive no `runner`, fora do `chat_service`.** Assim o
fallback é testável sem subir rota e sem sessão de chat. Descartado: laço dentro
de `chat_service.ask` — amarraria fallback a conversa, e ele precisa valer para
qualquer chamada.

**Erro repetível é lista explícita, não `except Exception`.** Timeout, erro de
conexão, 5xx, 429 e "modelo não encontrado" repetem. 401, 403, orçamento
estourado e recusa por política não repetem. Um erro desconhecido **não** repete
— errar para o lado de não gastar.

**`ai_run` é tabela nova, `ai_usage_day` fica.** Tentativa que falhou não tem
mensagem associada e não caberia em `ai_message`. `ai_usage_day` continua
sustentando o teto diário; a tela de consumo lê de `ai_run`, que é mais rico.
Descartado: derivar o teto diário de `ai_run` neste ciclo — mexeria num caminho
que funciona, sem ganho.

**A tela de consumo é página própria, o estado dos providers vai em Settings.**
São perguntas diferentes: "quanto gastei" é acompanhamento, "o DeepSeek está
conectado" é configuração. Descartado: um painel só — misturaria as duas.

## Schema e migração

Tabela nova, nenhuma coluna alterada, nenhum dado migrado.

```
ai_run
  id                integer, pk
  correlation_id    string(36), indexado    comum às tentativas da mesma pergunta
  attempt           integer                 1, 2, 3...
  provider          string(32)
  model             string(120)
  task_type         string(24)
  decision          string(8)               auto | manual
  tokens_in         integer
  tokens_out        integer
  latency_ms        integer
  status            string(8)               ok | timeout | error | skipped
  estimated_cost    numeric, nullable       null = não medido, nunca 0
  price_date        string(10), nullable     data da tabela de preço usada
  error             text, nullable          mensagem, já mascarada
  created_at        datetime
```

`estimated_cost` e `price_date` são anuláveis de propósito: **P-02**. Prompt e
resposta não têm coluna aqui — se um dia precisarem, é decisão de produto, não
detalhe de implementação.

**Reversão:** `downgrade` derruba a tabela. Nada mais depende dela, e a tela de
consumo degrada para "não medido" se ela sumir.

**Consequência operacional obrigatória (constituição, restrições técnicas):**
migração nova exige reconstruir e reinstalar o executável **na mesma sessão** —
`python -m PyInstaller devcockpit.spec --noconfirm`, parar o processo, trocar
`_internal` e `DevCockpit.exe`. Sem isso o painel instalado abre com "Can't
locate revision identified by '010_...'". Isso é uma task explícita, não um passo
implícito.

## Riscos

**1. Gravar tentativa durante o stream pode ressuscitar o `database is locked`.**
É o risco mais concreto: a Fase 3 já sofreu exatamente isso (`fbabea1`) porque o
repositório de mensagens só dava `flush`, deixando a transação aberta durante os
minutos do stream. Mitigação: o `runner` acumula as tentativas em memória e grava
em transação curta e própria, **depois** do stream fechar. Teste que prova que
uma escrita concorrente ao painel funciona durante uma resposta em curso.

**2. Toda pergunta passa a custar dinheiro.** DeepSeek e Kimi viram o padrão. O
teto de hoje é em tokens, não em dinheiro, e um teto em tokens calibrado para
modelo local pode significar bem mais gasto em nuvem. Mitigação: a tela de
consumo (REQ-12) mostra o custo do dia desde o primeiro commit que liga a nuvem,
e a pergunta em aberto sobre teto em R$ vai para o fim deste documento como item
a decidir — não vou inventar limite.

**3. `build_provider` é chamado pelos testes existentes.** Mudar sua assinatura
quebraria parte dos 647 testes. Mitigação: assinatura preservada, caminho novo
adicionado ao lado, e REQ-04 vira o teste que trava isso.

**4. A chave real pode vazar para o repositório.** Duas chaves reais entram no
`.env` desta máquina. `.env` e `.env.*` já estão no `.gitignore`, com exceção de
`.env.example`. Mitigação: além disso, o teste de REQ-14 varre resposta de rota
e HTML servido procurando o padrão; e `configs/ai.yml` entra no `.gitignore`.

**5. O identificador do Kimi e os preços podem estar errados.** Não confirmei
nenhum dos dois. Mitigação: vivem só no YAML (REQ-02, REQ-11); corrigir é editar
uma linha, e preço não confirmado entra ausente, virando "não medido".

**6. A janela do painel instalado pode seguir servindo código velho.** Já enganou
duas vezes numa sessão. Mitigação: parar o processo antes de reinstalar e
conferir que ele não voltou sozinho, como manda a memória do projeto.

## Estratégia de teste

**Automatizado, e é a maior parte.** A suíte roda sem rede, sem chave e sem
Ollama, conforme **P-06**:

- Registry: carga, arquivo ausente, YAML malformado, chave literal recusada,
  provider desabilitado fora do roteamento.
- Classificador: tabela de casos por `task_type`, mais a medição de tempo.
- Router: faixas de complexidade, precedência de `privacy: local`, recusa sem
  local, escolha manual vencendo, capacidade ausente caindo no padrão.
- Fallback: `FakeProvider` roteirizado para timeout → erro → sucesso; erro não
  repetível não gerando segunda tentativa; nenhum provider tentado duas vezes.
- Custo: com preço, sem preço, e a garantia de que ausência vira `null`.
- Providers: servidor de imitação para DeepSeek e para Kimi, no padrão de
  `tests/unit/test_ai_provider_wire.py`.
- Segurança: varredura por chave em resposta de rota, HTML e linhas de `ai_run`.
- Concorrência: escrita no painel durante stream em curso.

**Verificação manual, porque não dá para automatizar aqui:**

1. Pergunta real ao DeepSeek e ao Kimi com as chaves do usuário, conferindo
   texto, tokens e custo na tela.
2. Ollama parado, pergunta com `privacy: local` → recusa explicada, sem ir para
   a nuvem.
3. Chave do DeepSeek inválida de propósito → sem segunda tentativa.
4. Painel reconstruído e reinstalado, abrindo sem erro de revisão.

## Portão 2 — o que precisa do seu aval antes da fase 4

Um item se enquadra na regra de decisão difícil de reverter:

**Migração 010 e reinstalação do executável.** Aplicar a migração pelo Alembic do
repositório deixa o banco numa revisão que o bundle instalado não conhece, e o
painel que você usa todo dia para de abrir até ser reconstruído. É reversível
(`downgrade`), mas custa uma reinstalação no meio do caminho.

Não é decisão irreversível, e não vou pedir confirmação para ela agora — a task
que roda a migração vem acompanhada, na mesma task, da reconstrução e
reinstalação, para que o painel nunca fique num estado quebrado entre uma coisa e
outra.

## A decidir antes de ligar a nuvem

**Teto de gasto em dinheiro.** Hoje existe `DEVCOCKPIT_AI_DAILY_TOKEN_BUDGET =
200000`, calibrado para modelo local, onde token não custa. Com DeepSeek e Kimi
como padrão, esse número passa a representar dinheiro — e eu não sei qual valor
você aceita gastar por dia. Não vou escolher por você e não vou inventar um
padrão. Levo isso à sua decisão quando a tela de consumo estiver de pé e você
tiver visto o gasto real de alguns dias; até lá, o teto em tokens continua sendo
a única barreira, e a tela mostra o custo desde o primeiro dia.
