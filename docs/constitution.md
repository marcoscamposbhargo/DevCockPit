# Constituição — DevCockpit

Versão: 1.0.0 · Ratificada em: 2026-09-03 · Última alteração: 2026-09-03

Regras vinculantes deste projeto. Toda spec, plano e task herda estas regras sem
precisar repeti-las. Violação de princípio é bloqueio, não sugestão.

Esta constituição não inventa regra nova: consolida o que já está decidido nos
ADRs (`docs/adr/`), no modelo de segurança (`docs/07-security-model.md`) e nas
defesas do Cockpit AI. Onde houver divergência, o ADR específico manda e esta
constituição deve ser corrigida.

## Princípios

### P-01 — A IA não ganha capacidade que o painel não tenha por botão

Toda ação que a IA propõe existe antes como botão da interface, com sua rota e
seus testes. `app/services/ai/actions.py` é um catálogo fechado; cada entrada
aponta para a rota que o botão correspondente chama. O modelo escolhe um nome, o
servidor valida, a tela mostra, a pessoa confirma, e a execução vai pela rota de
sempre. Nome fora do registro, projeto inventado, JSON quebrado ou ação sem
projeto resolvido viram recusa — nunca uma ação aproximada.

Por quê: o produto é um painel de comando local com human-in-the-loop, não um
agente autônomo. Criar rota que existe só para a IA usar quebra o modelo de
segurança inteiro. (Defesa D-A3.)

Como se verifica: o teste que confere cada entrada de `actions.py` contra o
OpenAPI continua passando, e nenhuma rota nova é alcançável apenas pela IA.

### P-02 — O painel não afirma o que não mediu

Indicador sem dado não vira zero: vira "não medido", em cinza, dizendo o que
falta para poder ser medido. Score sai acompanhado da cobertura ("5 de 6"),
porque 67 com cinco indicadores e 67 com dois não são a mesma afirmação. "No ar"
só com prova. Custo que não dá para calcular é `null`, nunca `0`.

Por quê: o projeto inteiro se sustenta na tese de "fato, não palpite". Um número
inventado com aparência de medição é pior que a ausência do número, porque a
pessoa age em cima dele.

Como se verifica: para cada indicador exibido existe um caso de teste com a
fonte ausente, e ele prova que a tela mostra "não medido" em vez de zero.

### P-03 — Um processo, um arquivo de banco, sem etapa de build

O DevCockpit roda como um único processo FastAPI local, single-user, sobre um
SQLite (ADR-002), com frontend em ES modules servidos direto pelo FastAPI, sem
bundler e sem `node_modules` (ADR-005). É distribuído como executável
PyInstaller. Serviço novo, banco novo, broker novo ou etapa de build precisam
derrubar esta regra antes de entrar.

Por quê: o app é instalado com um atalho e aberto com um clique. Trocar isso por
"suba três containers antes de usar o painel" destrói a razão de ele existir. E
dois escritores no mesmo SQLite dão `database is locked` em botão sem relação
com o que estava sendo feito.

Como se verifica: `python -m PyInstaller devcockpit.spec` continua produzindo um
bundle que sobe sozinho, e o painel abre sem nenhum serviço externo obrigatório.

### P-04 — Comando externo só por allowlist, sem shell

Nada é executado por shell. `CommandRunner` recebe lista de argumentos e só
aceita executável que esteja na allowlist, com timeout (ADR-003). Requisição de
escrita exige `X-DevCockpit-Client: web` e `Origin` batendo com `settings.port`.

Por quê: a API é HTTP local, e qualquer página aberta no browser do usuário
consegue mandar requisição para ela. Sem allowlist e sem as duas checagens, uma
aba qualquer executa comando na máquina.

Como se verifica: os testes de `CommandRunner` e do middleware de origem
continuam passando; nenhuma chamada nova usa `shell=True`.

### P-05 — Segredo vive no ambiente e em nenhum outro lugar

Chave de API vem de variável de ambiente. Nunca é gravada no banco, nunca chega
ao frontend, nunca entra em log, nunca é versionada. A tela mostra o estado do
provider ("conectado", "não configurado"), jamais o valor. Prompt e resposta
passam por mascaramento antes de virar log (`app/services/ai/redaction.py`).

Por quê: o painel lê e monta contexto de 19 projetos reais; um log com chave
dentro vaza a chave em qualquer cópia do diretório de logs.

Como se verifica: teste que varre a resposta das rotas e as linhas de log
procurando o padrão de chave, e falha se encontrar.

### P-06 — Provider de modelo é substituível

Nenhuma regra de negócio depende de um SDK específico. Todo provider implementa
o mesmo contrato (`AIProvider` em `app/services/ai/providers.py`). O nome do
modelo é escolhido pelo servidor a partir da configuração; nada aceita nome de
modelo vindo do cliente. A aplicação continua funcional com a IA desligada e com
o provider local fora do ar.

Por quê: o conhecimento pertence ao projeto, o modelo é peça trocável. Acoplar a
um fornecedor transforma mudança de preço ou de política em reescrita.

Como se verifica: a suíte roda inteira com `FakeProvider`, sem rede e sem chave;
e desligar a IA não quebra nenhuma tela.

### P-07 — Comportamento novo chega com teste

Toda função principal tem teste automatizado, escrito no mesmo ciclo em que o
comportamento entra. Teste não depende de API real, de rede, nem de estado da
máquina de quem roda.

Por quê: é um painel que executa comandos e mexe em 19 projetos reais. A suíte é
a única coisa que separa "consertei" de "acho que consertei".

Como se verifica: `pytest -q` verde e `ruff check .` limpo antes de qualquer
commit.

## Restrições técnicas

- Python >= 3.11, FastAPI, SQLAlchemy, Alembic, Pydantic. `ruff` com
  `line-length = 100`.
- SQLite como banco. O arquivo efetivo do app instalado é
  `C:/Users/User/DevCockpit/data/devcockpit.db` — `settings.resolve` reescreve
  caminho relativo, e conferir o arquivo do repositório engana.
- Migração nova exige reconstruir e reinstalar o executável na mesma sessão: o
  bundle PyInstaller carrega o próprio catálogo de migrações, e o banco é
  compartilhado.
- Windows 11 é a plataforma primária; toda ação de SO passa pelo `OSAdapter`
  (ADR-007).
- Frontend em ES modules, sem dependência externa e sem etapa de build.
- Operação longa vira job assíncrono com progresso por SSE (ADR-006).
- Uma instância do painel por vez. O launcher identifica quem está na porta pela
  assinatura do `/api/health` e traz a janela existente para a frente.

## Fora de escopo permanente

- Agente autônomo que executa sem confirmação da pessoa.
- Terminal irrestrito exposto à IA.
- Comando destrutivo disparado por modelo (`rm`, `git push`, `git reset --hard`,
  `docker system prune` e equivalentes).
- Escrita de arquivo dentro de projeto alheio sem que isso seja primeiro um
  botão do painel, com rota e testes próprios (decorre de P-01).
- Chave de API editável ou visível pela interface.
- Multiusuário, autenticação de rede, exposição fora de `127.0.0.1`.

## Governança

- Alterar esta constituição exige aprovação explícita do dono do projeto.
- Versionamento SemVer: MAJOR remove ou inverte princípio, MINOR adiciona,
  PATCH esclarece redação sem mudar obrigação.
- Toda alteração registra abaixo o que mudou e por quê.

## Histórico

- 1.0.0 (2026-09-03) — versão inicial. Consolida ADR-001 a ADR-009, o modelo de
  segurança e as defesas D-A1/D-A3 do Cockpit AI em sete princípios, escrita na
  fase 0 do ciclo spec-driven do AI Harness.
