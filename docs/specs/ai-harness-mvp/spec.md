# Spec — AI Harness MVP

Feature: `ai-harness-mvp` · Criada em 2026-09-03
Origem: `PRD — DEVCOCKPIT AI HARNESS / HYPERBRAIN`, seções 43 e 49
Constituição: `docs/constitution.md` v1.0.0

## Problema

O Cockpit AI funciona hoje — três especialistas, catálogo fechado de doze ações,
auditoria com `actor=ai`, teto diário de tokens — mas a camada de modelo abaixo
dele é rasa, e isso aparece de quatro formas concretas:

1. **Um provider por vez, e se ele cair a pergunta morre.** `build_provider`
   (`app/services/ai/providers.py:456`) lê `DEVCOCKPIT_AI_PROVIDER` e monta
   exatamente um. Com o Ollama parado, ou com um nome de modelo que não existe
   naquela instalação, a resposta é um erro e acabou. Não há segunda tentativa
   em lugar nenhum.

2. **Não existe catálogo de modelos.** Há duas variáveis,
   `DEVCOCKPIT_AI_MODEL` e `DEVCOCKPIT_AI_MODEL_ALT`, e um `_modelo` que faz
   perfil desconhecido cair no padrão. Nada declara que um modelo serve para
   código e outro para conversa curta, nem quanto cada um custa. A escolha entre
   os dois é do perfil de especialista, não da tarefa.

3. **O consumo é agregado e cego.** `ai_usage_day` guarda três números por dia:
   tokens de entrada, de saída e chamadas. Isso sustenta o teto diário e nada
   mais. Não dá para responder qual provider gastou, quanto demorou, se houve
   tentativa que falhou antes da que deu certo, nem quanto aquilo custou em
   dinheiro. A medição do próprio usuário — 24 a 32 tok/s no `qwen2.5-coder:7b`
   nesta máquina — mora numa anotação, não no painel.

4. **O contexto ignora documentação estruturada.** O Context Engine lê
   `README.md`, `CLAUDE.md`, `AGENTS.md` e `devcockpit.yml`
   (`app/services/ai/context_engine.py:37`). Um projeto que descreva sua
   arquitetura e suas decisões em arquivos próprios não tem como oferecer isso
   ao painel.

## Objetivo

Dar ao Cockpit AI um registro declarativo de providers e modelos, fallback real
entre eles, classificação de tarefa que orienta a escolha, e um registro por
execução com custo e latência — tudo dentro do processo único que já existe, sem
ampliar o que a IA pode fazer.

## Fora de escopo

Esta seção existe para não reabrir discussão a cada task. O PRD de origem pede
todos os itens abaixo; nenhum entra neste ciclo.

**Barrado por princípio da constituição:**

- Serviço `services/ai-harness/` separado, PostgreSQL, Redis ou Docker Compose
  novo (PRD §7 e §37). Viola **P-03** — um processo, um arquivo de banco, sem
  etapa de build. O painel é distribuído como executável PyInstaller e aberto
  com um clique.
- Developer Agent que cria, edita ou refatora arquivos (PRD §23). Viola
  **P-01** — a IA não ganha capacidade que o painel não tenha por botão.
- Botão que escreve o esqueleto do `.project-ai/` dentro de projeto alheio.
  Escrita em projeto de terceiro é capacidade nova; teria de virar botão com
  rota e testes próprios antes (decorre de **P-01**).
- Chave de API editável ou visível pela tela. Mostrar o *estado* do provider é
  permitido; mostrar o valor não. Fora de escopo permanente por **P-05**.
- Terminal, deploy, `delete_file` e `git_push` como ferramenta de IA (PRD §27,
  lista "posteriormente").

**Adiado por fase, não por princípio:**

- RAG, chunking, embeddings, reranking, citações, banco vetorial e pgvector
  (PRD §18). É a Fase 2 do próprio PRD.
- Judge / Evaluation Engine, multi-agent, execução paralela, benchmark
  (PRD §26 e §45). Fase 3 do PRD.
- Roteamento adaptativo que aprende com histórico (PRD §46). Fase 4 do PRD, e
  depende de o registro por execução desta spec existir primeiro.
- vLLM e OpenCode (PRD §10 e §29).
- Agentes novos além dos três especialistas atuais — Planner, Architect, Test,
  Documentation, Data (PRD §20). Os três de hoje cobrem os itens 12, 13 e 14 do
  MVP do PRD.
- Groq, OpenRouter, Mistral, Together e Gemini como providers declarados e
  testados (PRD §11). Com o provider genérico do REQ-05, os quatro primeiros
  passam a ser declaráveis sem código novo — mas declarar, testar e precificar
  cada um é escopo próprio. Gemini tem formato de API distinto e precisaria de
  classe. Nada disso entra neste ciclo.
- `POST /ai/tasks` e `GET /ai/tasks/{id}` como fila assíncrona de IA (PRD §38).
  Já existe `ai_task` com outra semântica; unificar é conversa própria.
- Memória de longo prazo seletiva e memória operacional (PRD §19). `ai_memory`
  já existe e não muda aqui.

## Requisitos

### Registro declarativo

**REQ-01** — O sistema lê `configs/ai.yml` na inicialização e monta a partir
dele o registro de providers, com pelo menos: identificador, `enabled`, `type`
(`local` ou `cloud`), `base_url` e o nome da variável de ambiente que carrega a
chave (`api_key_env`). Provider com `enabled: false` não é considerado em
nenhuma decisão de roteamento.

**REQ-02** — O mesmo arquivo declara o registro de modelos, separado do de
providers, com: identificador lógico, nome real do modelo, lista de
`capabilities`, lista ordenada de `providers` que sabem servi-lo, e `cost_tier`
(`free`, `low`, `high`). Nenhum nome de modelo real passa a aparecer codificado
fora deste arquivo e dos padrões já existentes em `MODELO_PADRAO`.

**REQ-03** — Nenhuma chave de API aparece em `configs/ai.yml`. O arquivo nomeia
a variável de ambiente; o valor é lido do ambiente no momento de montar o
provider. Arquivo de configuração contendo algo que se pareça com uma chave faz
a carga falhar com erro explícito, em vez de aceitar em silêncio.

**REQ-04** — Na ausência de `configs/ai.yml`, o sistema continua funcionando
exatamente como hoje, montando um provider único a partir de
`DEVCOCKPIT_AI_PROVIDER`, `DEVCOCKPIT_AI_MODEL` e `DEVCOCKPIT_AI_API_KEY`.
Arquivo ausente não é erro. Um `configs/ai.example.yml` versionado documenta o
formato, seguindo o padrão de `configs/roots.example.yml`.

**REQ-05** — Existe um provider para APIs compatíveis com o formato
`/v1/chat/completions`, parametrizado por `base_url` e chave, servindo DeepSeek
e Kimi (Moonshot) a partir da declaração no registry — sem uma classe por
fornecedor. Ele mantém streaming e contagem de tokens como os providers atuais,
e é exercitado por teste contra servidor de imitação de cada um. As chaves vêm
de `DEVCOCKPIT_AI_KEY_DEEPSEEK` e `DEVCOCKPIT_AI_KEY_MOONSHOT`. Se a API de
algum dos dois divergir do formato em algum ponto (contagem de tokens no
stream, campo de erro), a divergência vira subclasse pequena e não uma cópia do
provider inteiro.

### Roteamento

**REQ-06** — Antes de escolher modelo, o sistema classifica a pergunta por regra
determinística e produz `task_type` (um de: `simple_task`, `coding`,
`debugging`, `architecture`, `documentation`, `testing`, `qa`, `planning`,
`refactoring`), `complexity` (0 a 100), `privacy` (`local` ou `internal`) e
`tools_required` (booleano). A classificação não faz chamada a modelo nenhum e
responde em menos de 50 ms.

**REQ-07** — O Model Router escolhe o modelo a partir da classificação, por
política determinística e legível, nesta ordem de precedência:

1. `privacy == local` vai para um modelo local, sempre, sem consultar
   complexidade. Não havendo modelo local habilitado, a pergunta é **recusada**
   com explicação — nunca promovida para a nuvem.
2. Caso contrário, a complexidade decide entre os modelos cloud habilitados que
   tenham a capacidade pedida: até 40, o mais barato; acima de 40, o de janela
   maior. **O modelo local que declare a mesma capacidade entra ao final desta
   lista**, depois de todo candidato de nuvem — nunca disputa "o mais barato"
   nem "a maior janela" (por isso fica fora do critério de ordenação), mas
   segue sendo candidato de último recurso quando a nuvem inteira falhar.
   Restrição manual de provider (REQ-08) não se estende ao local: pedir um
   provider específico é a pessoa dizendo "só este endereço", e completar por
   baixo dela com o local seria contrariar o pedido.
3. Sem candidato com a capacidade pedida, cai no modelo padrão configurado em
   vez de falhar.

A política vive num único lugar legível e é alterável por `configs/ai.yml`. Os
limiares são configuração, não constante espalhada.

**Correção de 2026-09-04, por verificação ao vivo da T-14.** A primeira
implementação do item 2 excluía o local da lista de candidatos por completo
(certo, para não disputar "o mais barato" — ver a nota de premissa abaixo),
mas não o reintroduzia como último recurso depois. Com DeepSeek e Kimi sem
saldo e o Qwen local saudável e de pé, a pergunta falhava sem nunca oferecer
o local como candidato — o comentário do próprio `configs/ai.yml` sobre "o
local é a rede de segurança sem internet" não correspondia ao que o código
fazia. `_modelos_de_nuvem` continua excluindo o local do critério de
ordenação; o que mudou é que ele entra depois, como último candidato da fila
que o runner consome.

**Nota de premissa.** A meta LOCAL FIRST do PRD (§3 e §48: 70–80% das tarefas
locais) **não se aplica a esta máquina** e não é critério de aceite deste ciclo.
Medição: 24 a 32 tok/s no `qwen2.5-coder:7b`, sem GPU dedicada — uma pergunta
com contexto real leva minutos. O local fica na cadeia pelos dois motivos que
sobrevivem à medição: privacidade (item 1 acima) e último elo do fallback quando
não há internet. Economia deixa de ser a razão de ele existir.

**REQ-08** — Escolha manual da pessoa vence o roteamento automático. Quando a
tela envia modelo ou provider explícito, o router registra a decisão como
`manual` e não sobrepõe. O modo AUTO é o padrão.

**Precedência sobre REQ-07, desambiguada em 2026-09-03.** "Vence o roteamento
automático" significa vencer o **item 2** do REQ-07 — qual modelo — e não o
**item 1** — se a pergunta pode sair da máquina. Escolha manual de modelo cloud
numa pergunta classificada como `privacy: local` **não** vale: a decisão segue
local e o motivo diz que o pedido foi ignorado, para a pessoa saber que sua
escolha não valeu e poder retirar a marca de privacidade se foi engano.
Privacidade é portão, não preferência. Escolha manual com identificador
desconhecido cai no automático, sem levantar e sem mandar o nome cru ao
fornecedor.

**REQ-09** — Quando uma tentativa falha, o sistema tenta o próximo candidato da
cadeia declarada em `configs/ai.yml`, até um máximo configurável de tentativas
(padrão 3). Nenhum provider é tentado duas vezes na mesma execução — é essa
regra, não o motivo do erro, que evita repetir uma tentativa inútil contra o
mesmo provider que já falhou (chave inválida, sem saldo, recusa por política).
Erro de um provider nunca impede a tentativa do próximo: chave inválida ou
saldo esgotado na DeepSeek não diz nada sobre o Kimi, que é outra conta e outro
endereço. O único bloqueio que interrompe a cadeia **inteira antes de começar**
é `_exigir_orcamento()` — o teto diário é limite nosso, não falha de provider,
e por isso nunca gera tentativa nem consome a cadeia.

**Correção de 2026-09-04, por verificação ao vivo da T-14.** A primeira
implementação lia "erro que não adianta repetir... não dispara fallback" como
"para a cadeia inteira", e a chave da DeepSeek sem saldo (402) impediu até o
Kimi, saudável, de ser tentado. Esse não é o comportamento que se quer: o
critério certo de "vale a pena tentar de novo" é sempre por *provider*, nunca
pela cadeia como um todo.

### Observabilidade e custo

**REQ-10** — Cada execução grava uma linha por tentativa contendo:
`correlation_id` comum às tentativas da mesma pergunta, número da tentativa,
provider, modelo, `task_type`, tokens de entrada e saída, latência em
milissegundos, status (`ok`, `timeout`, `error`, `skipped`) e a mensagem de erro
quando houver. Prompt e resposta não entram nessa linha.

**REQ-11** — O custo estimado em dinheiro sai da tabela de preço declarada por
modelo em `configs/ai.yml`, que carrega a data em que o preço foi anotado.
Modelo sem preço declarado grava `estimated_cost = null` e a tela mostra "não
medido", nunca zero (**P-02**). Onde o custo aparecer, a data da tabela aparece
junto.

**REQ-12** — Existe uma visão de consumo no painel mostrando, para o período:
chamadas, tokens de entrada e saída, divisão entre uso local e cloud, custo
estimado com a ressalva de data, latência média, contagem de falhas e contagem
de fallbacks acionados. Indicador sem dado segue **P-02**.

**REQ-13** — Um endpoint de saúde relata, para cada provider habilitado, se ele
responde e quais modelos oferece. Provider fora do ar é reportado como
indisponível sem derrubar a resposta dos demais nem impedir o painel de abrir.

**Limite conhecido de "disponível", medido em 2026-09-20.** A sondagem é um
`GET /v1/models`, que mede **alcance**, não **capacidade de gerar**. Uma conta
sem saldo (DeepSeek, `402 Insufficient Balance`) ou suspensa (Moonshot,
`429 account suspended`) lista modelos normalmente e aparece como
`disponivel: true` — e só falha na primeira pergunta real. Isso não é defeito
do healthcheck: sondar com uma geração de verdade custaria dinheiro a cada
abertura da tela de configurações, o que seria pior. Onde a diferença importa
é no diagnóstico: "disponível" aqui significa "responde e tem chave aceita",
e a prova de que o provider **gera** está em `ai_run`, não nesta rota.

**REQ-14** — A tela de configurações lista os providers declarados com o estado
de cada um: conectado, não configurado, desligado ou indisponível. O valor da
chave nunca aparece, nem inteiro nem parcialmente mascarado.

### Contexto

**REQ-15** — O Context Engine passa a considerar os arquivos de `.project-ai/`
do projeto (`PROJECT.md`, `ARCHITECTURE.md`, `SPECS.md`, `RULES.md`,
`DECISIONS.md`, `TASKS.md`, `MEMORY.md`) como fonte de documento, sujeitos à
mesma seleção por relevância e ao mesmo teto de tokens que as fontes atuais.
Pasta ausente não é erro e não muda o comportamento de hoje.

## Critérios de aceite

| REQ | Como se prova |
|---|---|
| REQ-01 | Teste carrega um `ai.yml` com dois providers, um `enabled: false`, e verifica que só o habilitado aparece no registro e nas decisões de roteamento. |
| REQ-02 | Teste consulta o registro por capacidade (`coding`) e recebe os modelos declarados, na ordem de provider declarada. Varredura do `app/` não encontra nome de modelo real novo fora de `providers.py`. |
| REQ-03 | Teste com `ai.yml` contendo `api_key: sk-...` faz a carga levantar erro nomeando o arquivo. Teste com `api_key_env` monta o provider lendo do ambiente. |
| REQ-04 | Suíte roda com `configs/ai.yml` ausente e todos os testes atuais do Cockpit AI continuam passando sem alteração. |
| REQ-05 | Teste sobe servidor de imitação para DeepSeek e para Kimi, exercita `stream` e `complete` em cada um, e confere texto acumulado e tokens. Um terceiro teste prova que os dois usam a mesma classe, diferindo só por configuração. Verificação ao vivo com a chave real do usuário fecha o REQ. |
| REQ-06 | Tabela de casos: para cada `task_type`, ao menos uma pergunta de exemplo produz a classificação esperada. Teste mede que classificar 100 perguntas fica abaixo de 50 ms cada. |
| REQ-07 | Teste alimenta classificações sintéticas de complexidade 10, 50 e 90 e confere o modelo escolhido em cada faixa. Teste com `privacy: local` confere que o escolhido é local mesmo com complexidade 95; e que, sem modelo local habilitado, a pergunta é recusada — teste que falha se a escolha cair em provider `type: cloud`. Caso sem candidato com a capacidade cai no padrão e não levanta. Teste confere que o local aparece como **último** candidato da lista (nunca primeiro, nunca ausente) quando declara a mesma capacidade; e que restrição manual de provider não o inclui. |
| REQ-08 | Teste envia modelo explícito junto da pergunta e confere que o registro da execução marca `manual` e usa o modelo pedido, mesmo com a regra apontando outro. |
| REQ-09 | Com `FakeProvider` configurado para timeout, depois erro, depois sucesso: a resposta chega, três linhas de tentativa são gravadas e a última tem status `ok`. Teste separado prova que chave inválida na primeira conta AVANÇA para a segunda (provider diferente) e responde; e que dois candidatos do MESMO provider nunca chamam o segundo. |
| REQ-10 | Depois de uma pergunta com fallback, consultar o registro pelo `correlation_id` devolve as tentativas em ordem, com latência preenchida. Teste varre as linhas procurando trecho do prompt e não encontra. |
| REQ-11 | Modelo com preço declarado gera `estimated_cost` numérico coerente com tokens × preço. Modelo sem preço gera `null`, e a rota de consumo traz "não medido" em vez de `0`. |
| REQ-12 | Rota de consumo devolve todos os campos listados; teste com banco vazio confere que os indicadores vêm como não medidos, não como zero. Verificação visual na tela fecha o REQ. |
| REQ-13 | Com dois providers declarados e um deles apontando para porta fechada, a rota de saúde devolve 200, marca um como disponível e o outro como indisponível com motivo. |
| REQ-14 | Teste varre a resposta da rota de configurações e o HTML servido procurando o valor da chave de teste, e falha se encontrar. Estado exibido bate com o do registry. |
| REQ-15 | Projeto de teste com `.project-ai/ARCHITECTURE.md` tem o conteúdo do arquivo no contexto montado. Projeto sem a pasta produz o mesmo contexto de antes da mudança. |

## Casos de borda e erro

- **`configs/ai.yml` malformado:** o painel abre, a IA reporta "não configurada"
  com o erro de parse nomeando o arquivo, e o resto do DevCockpit funciona.
  Nunca derrubar a inicialização por causa da IA (**P-06**).
- **Provider declarado com `api_key_env` apontando para variável ausente:**
  estado "não configurado", excluído do roteamento e do fallback, sem erro na
  abertura.
- **Todos os providers da cadeia falham:** erro único ao usuário dizendo quantas
  tentativas houve e o motivo da última, com as tentativas gravadas. Não repetir
  a cadeia.
- **Teto diário de tokens estourado:** interrompe **antes** da cadeia começar —
  orçamento é checado uma vez, no início, não "no meio"; não é falha de
  provider e não consome tentativa (REQ-09).
- **Chave inválida ou sem saldo num provider da cadeia:** não impede o próximo
  candidato, que é sempre outro provider — `_fila()` nunca oferece o mesmo
  provider duas vezes (REQ-09, corrigido em 2026-09-04).
- **Ollama no ar mas sem o modelo instalado:** conta como falha que dispara
  fallback, com o nome do modelo na mensagem, porque é o erro mais comum nesta
  máquina.
- **Sem internet:** os providers cloud entram como indisponíveis e a cadeia
  termina no modelo local. A resposta chega, lenta, e o registro da execução
  mostra as tentativas que falharam antes. Se nem o local estiver de pé, o erro
  diz que a IA está indisponível e o resto do painel segue funcionando.
- **Pergunta classificada como `privacy: local` sem modelo local habilitado:**
  recusa explicando o motivo. Nunca promover para a nuvem — é o caso em que
  errar significa mandar para fora o que não podia sair (REQ-07, item 1).
- **Resposta malformada do provider (JSON quebrado no meio do SSE):** conta como
  falha e dispara fallback; o texto parcial já emitido não é gravado como
  resposta boa.
- **Latência do provider local:** medido nesta máquina, 24 a 32 tok/s no
  `qwen2.5-coder:7b`. Uma pergunta com contexto de 12 mil tokens leva minutos. O
  timeout precisa acomodar isso sem virar fallback indevido, e o teto de
  contexto existente (`ai_max_context_tokens = 12000`) continua valendo.
- **Escrita no SQLite durante stream longo:** a Fase 3 já corrigiu o caso em que
  a transação ficava aberta durante o stream inteiro e travava toda escrita do
  painel (`fbabea1`). As linhas de tentativa do REQ-10 não podem reintroduzir
  isso.
- **`.project-ai/` com arquivo gigante:** sujeito ao mesmo teto de tokens; entra
  truncado ou não entra, e o contexto diz qual bloco ficou de fora.
- **`.project-ai/` com link simbólico apontando para fora do projeto:** não
  seguir.

## Perguntas em aberto

1. **Onde a linha por tentativa mora.** A spec exige o registro (REQ-10) mas não
   fixa se é tabela nova (`ai_run`) ou colunas em `ai_message`. Assunção
   adotada: **tabela nova**, porque tentativa que falhou não tem mensagem
   associada e caberia mal numa coluna de mensagem. Decisão final no plano
   (fase 3), junto da migração e da nota sobre reconstruir o executável.

2. **Se `ai_usage_day` sobrevive.** Com a linha por tentativa, o agregado diário
   vira derivável. Assunção adotada: **mantém**, porque é o que sustenta o teto
   diário hoje e removê-lo é risco sem ganho neste ciclo.

3. **Identificador exato dos modelos cloud.** Decidido com o usuário: DeepSeek e
   Kimi (Moonshot) são os modelos de trabalho; o local fica para `privacy:
   local` e offline. O identificador do Kimi **não está confirmado** — conheço
   `kimi-k2` e a variante de raciocínio; um "K3" seria posterior ao meu corte de
   conhecimento. Assunção adotada: o `ai.example.yml` declara o id que o usuário
   confirmar no momento da implementação, e o campo vive só no YAML (REQ-02),
   então corrigir é uma linha. O mesmo vale para `base_url` de cada um.

4. **Preço de DeepSeek e Kimi na tabela.** Não tenho como confirmar o preço
   vigente. Assunção adotada: escrever a tabela com os valores que o usuário
   consultar no painel de cada fornecedor, com a data (REQ-11). Modelo sem preço
   confirmado entra sem preço e aparece como "não medido" — nunca com valor
   chutado (**P-02**).

5. **Verificação ao vivo dos providers cloud.** O usuário confirmou ter a chave
   da DeepSeek; a da Moonshot (Kimi) não foi confirmada. As duas vão em
   `DEVCOCKPIT_AI_KEY_DEEPSEEK` e `DEVCOCKPIT_AI_KEY_MOONSHOT` no `.env` local,
   nunca no repositório. Se a verificação ao vivo não couber na sessão, ou se
   faltar a chave da Moonshot, REQ-05 fecha com o servidor de imitação e a
   verificação real fica anotada como pendência explícita — não como REQ
   cumprido (**P-02**).

6. **A spec não foi revisada por terceiro.** O portão 1 é a revisão do próprio
   usuário.
