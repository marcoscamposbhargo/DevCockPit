# 10 — Estratégia de Testes

Escrita antes da implementação, conforme o item 26 do prompt.

## Problema central

O DevCockpit existe para falar com Git, Docker e sistema operacional. Testar
isso ingenuamente produz uma suíte que só passa na máquina de quem escreveu,
depende do Docker estar ligado e leva minutos para rodar.

A resposta é arquitetural, não de ferramenta: **o `CommandRunner` é uma
fronteira injetável**. Acima dela, tudo é testável sem tocar no SO. Abaixo,
existe um punhado de testes de integração lentos e marcados.

## Pirâmide

```
        ┌──────────────────────────┐
        │  e2e manual (checklist)  │  por fase, ~10 casos
        ├──────────────────────────┤
        │  integração (marcados)   │  git real, docker real
        ├──────────────────────────┤
        │  API (TestClient)        │  contrato HTTP + segurança
        ├──────────────────────────┤
        │  unitários               │  a maior parte
        └──────────────────────────┘
```

## Ferramentas

`pytest`, `pytest-asyncio`, `pytest-cov`, `httpx` + `TestClient`.
Sem mock de biblioteca de terceiro por monkeypatch de `subprocess`: a
substituição é por injeção de dependência.

## Marcadores

```ini
markers =
    unit
    api
    integration_git
    integration_docker
    slow
```

Padrão local e em pipeline: `pytest -m "not integration_docker and not slow"`.
Docker não pode ser pré-requisito para a suíte rodar.

## Camada 1 — Unitários

### Dois runners, dois dublês

Existe um `CommandRunner` síncrono (leituras rápidas) e um `AsyncCommandRunner`
(jobs). **Dublar só o primeiro não basta.**

Isto foi aprendido do jeito difícil: um teste de API que enfileirava
`docker compose up` chegou a subir containers de verdade na máquina de
desenvolvimento, porque o `JobManager` seguia usando o runner assíncrono real.
O teste passou; o efeito colateral só apareceu num `docker ps` posterior.

Duas defesas hoje:

1. `tests/conftest.py` dubla `app.state.job_manager.runner` no client padrão;
2. uma fixture `autouse` **bloqueia** `AsyncCommandRunner.run` em qualquer teste
   não marcado como integração, falhando com mensagem explícita em vez de
   mexer no ambiente de quem roda a suíte.

### `FakeCommandRunner`

Peça central da estratégia. Recebe um mapa de `label` para `CommandResult` e
grava todo `CommandSpec` executado.

```python
runner = FakeCommandRunner({
    "git.status": CommandResult(0, GIT_STATUS_DIRTY_FIXTURE, "", 12, False),
})
service = GitService(runner=runner, cache=NullCache())
```

Permite asserção nos dois lados: o que o adapter **produziu** (argv exato) e o
que o service **entendeu** da saída.

### O que cobrir

| Alvo | Casos |
|------|-------|
| `core/paths.py` | path relativo; inexistente; arquivo em vez de diretório; fora do root; `..` escapando; symlink escapando; caixa diferente no Windows; root com prefixo parecido (`Desktop` vs `Desktop-antigo`) |
| `runner/allowlist.py` | ação conhecida; desconhecida; placeholder com valor inválido; valor começando com `-` |
| `GitAdapter` | argv esperado; parse de repo limpo, sujo, staged, untracked, detached, sem upstream, com ahead/behind; caminho com espaço; caminho com acento; saída vazia; exit code diferente de zero |
| `DockerAdapter` | argv esperado; parse de `ps --format json`; JSON por linha; saída vazia; daemon fora do ar; JSON malformado |
| `OSAdapter` | argv por plataforma para VS Code, pasta, terminal, browser |
| `DetectionRegistry` | cada um dos 12 detectores; projeto com múltiplas stacks; nenhuma stack; `detection_locked` preservando `MANUAL` |
| `JobManager` | ciclo completo; timeout; cancelamento; exclusão mútua na mesma chave; chaves diferentes em paralelo; saída incremental |
| `TTLCache` | hit, expiração, invalidação, marcação `STALE` |
| `ServiceHealthService` | ONLINE, OFFLINE, timeout vira ERROR, TCP sem HTTP, `health_kind: none` ignorado |
| Serviços | unicidade de path, projeto `MISSING`, agregação do dashboard |
| Redação de log | argv com `token=` mascarado |

### Fixtures

`tests/fixtures/` guarda **saída real** capturada das ferramentas:

```
git/status_clean.txt          status_dirty.txt
git/status_detached.txt       status_no_upstream.txt
git/log_format.txt
docker/compose_ps_running.json    compose_ps_empty.json
docker/compose_ps_malformed.json  daemon_down_stderr.txt
compose/simple.yml            compose/multi_service_ports.yml
```

Regra: fixture é capturada de execução real, com a versão da ferramenta anotada
no topo. Fixture inventada à mão é a origem clássica do teste que passa e do
código que falha.

## Camada 2 — API

`TestClient` com banco SQLite em memória, `FakeCommandRunner` e allowlist de
roots apontando para `tmp_path`.

| Grupo | Casos |
|-------|-------|
| Contrato | status code e schema de cada endpoint do `06` |
| Erro | cada `code` da tabela de erros é alcançável |
| Segurança | os 12 testes de `07-security-model.md` |
| Assíncrono | ação longa devolve 202 + `job_id`; polling chega a estado final |
| Concorrência | segundo `up` na mesma chave devolve 409 |
| Degradação | Docker indisponível: `/dashboard` responde 200 |

Os testes de segurança do `07` são **bloqueantes de merge**. Falha ali não vira
issue: reprova a entrega.

## Camada 3 — Integração

### Git real (`integration_git`)

Rápido e determinístico, então roda por padrão. Cada teste constrói seu
repositório em `tmp_path`:

```
git init -> commit inicial -> cenário (modifica, adiciona, remove, branch)
-> exercita o GitAdapter real -> valida
```

Cenários: repo limpo, sujo, arquivo novo, arquivo removido, staged, branch
diferente, detached HEAD, remote configurado, path com espaço e com acento.

Nunca opera em repositório do usuário.

### Docker real (`integration_docker`)

Desativado por padrão. Usa um `docker-compose.test.yml` mínimo em
`tests/fixtures/` com uma imagem leve. Cenários: `up`, `ps`, `logs`, `down`,
daemon desligado.

### Filesystem (`integration`)

Descoberta em árvore temporária: projetos aninhados, `node_modules` para ser
ignorado, profundidade além do limite, diretório sem permissão, symlink.

## Camada 4 — Checklist manual por fase

Automatizar "o VS Code abriu" não vale o custo. Cada fase tem checklist no
`PROJECT_STATUS.md`. Exemplo da Fase 4:

```
[ ] botão VS Code abre o projeto correto
[ ] botão Pasta abre o Explorer no diretório certo
[ ] botão Terminal abre já posicionado no diretório
[ ] botão Abrir App abre a URL certa no browser
[ ] com `code` fora do PATH, o botão aparece desabilitado com motivo
[ ] dashboard com 30 projetos carrega sem travar
```

## Metas de cobertura

| Camada | Mínimo | Motivo |
|--------|--------|--------|
| `core/paths.py` | 100% | é defesa de segurança |
| `runner/` | 95% | é defesa de segurança |
| `detection/` | 90% | lógica pura, barato de cobrir |
| `services/` | 80% | regra de negócio |
| `adapters/` | 80% | parse é onde o bug se esconde |
| `api/` | 70% | contrato |
| frontend | sem meta no MVP | coberto por checklist manual |

Cobertura é piso, não objetivo. Vale mais um teste de parse com fixture real do
que dez testes de getter.

## Anti-padrões proibidos

| Proibido | Em vez disso |
|----------|--------------|
| teste unitário chamando `subprocess` real | `FakeCommandRunner` |
| teste que depende do Docker Desktop ligado | marcador `integration_docker` |
| teste operando em repositório do usuário | repo em `tmp_path` |
| fixture escrita à mão imitando saída de ferramenta | captura real, com versão anotada |
| asserção só no retorno do service | asserção também no argv produzido |
| `sleep` para sincronizar job | espera por condição com timeout |
| teste tocando `configs/roots.yml` real | roots injetados apontando para `tmp_path` |
| dublar só o `CommandRunner` síncrono | dublar **também** `job_manager.runner`; jobs usam o runner assíncrono |

## Definição de pronto

Uma entrega só está pronta quando:

1. testes unitários da lógica nova passam;
2. testes de contrato dos endpoints novos passam;
3. testes de segurança aplicáveis passam;
4. cobertura da camada não caiu;
5. o documento correspondente em `docs/` foi atualizado;
6. o checklist manual da fase foi executado;
7. `PROJECT_STATUS.md` foi atualizado.
