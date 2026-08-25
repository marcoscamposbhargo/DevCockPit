<div align="center">

<img src="frontend/assets/devcockpit.png" alt="DevCockpit" width="96">

# DevCockpit

**Central local dos seus projetos de desenvolvimento.**
Um lugar só para saber o que você tem, o que está no ar, o que tem alteração pendente e qual porta é de quem — e operar tudo isso sem abrir terminal.

[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![SQLite](https://img.shields.io/badge/SQLite-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Testes](https://img.shields.io/badge/testes-496%20passando-3fb950)](#testes)
[![Cobertura](https://img.shields.io/badge/cobertura-88%25-3fb950)](#testes)
[![Ruff](https://img.shields.io/badge/lint-ruff-261230?logo=ruff&logoColor=white)](https://docs.astral.sh/ruff/)
[![Plataforma](https://img.shields.io/badge/Windows-11-0078D4?logo=windows&logoColor=white)](#plataforma)

</div>

---

## O problema

Manter 30 projetos locais é manter 30 conjuntos de conhecimento operacional na cabeça: onde a pasta está, qual comando sobe, qual porta usa, qual container é de qual projeto, o que ficou sem commit. Retomar um projeto parado há três semanas custa de 5 a 15 minutos de arqueologia — e a conta se paga várias vezes por dia.

Toda essa informação já está no disco. O DevCockpit lê, guarda o que não é derivável e põe as ações a um clique.

## O que ele faz

| | |
|---|---|
| **Descobre** | varre uma pasta raiz e encontra os projetos: 31 achados em 0,19 s num Desktop real |
| **Identifica** | detecta a stack por marcadores (`pyproject.toml`, `package.json`, `docker-compose.yml`, `vite.config.*`…) e extrai as portas declaradas |
| **Observa** | quem está escutando em cada porta, **com prova de dono** — e conflitos marcados na linha |
| **Opera** | liga e desliga o ambiente: Compose e servidor de desenvolvimento, na ordem certa |
| **Acompanha** | health check dos serviços locais, com histórico e disponibilidade ponderada por tempo |
| **Mostra o Git** | branch, arquivos sujos, commits, remotes — **somente leitura**, sempre |
| **Abre** | VS Code, pasta, terminal e o app no navegador, já no diretório certo |
| **Registra** | auditoria de tudo que foi executado, com desfecho, duração e motivo |

E responde "e antes?": atividade por dia, horário de trabalho e uso de stack, a partir do que o próprio painel mediu.

## Uma decisão de projeto que atravessa tudo

> **Prova afirma, inferência sugere, ausência se cala.**

Um painel que diz "no ar" quando não sabe é pior que um painel que não diz nada — depois da segunda vez, ninguém acredita na tela.

Exemplo real: dois projetos declarando a porta 8000, um deles parado. O painel dizia que os dois estavam rodando, porque a verificação de saúde abre um socket e pergunta *"tem alguém aí?"*, nunca *"quem?"*. Hoje a atribuição de porta de container vem do rótulo do Compose — que é fato, não dedução —, e o que não tem prova aparece como **"porta ocupada"**, fora da contagem de projetos rodando.

## Segurança

O DevCockpit executa comandos na sua máquina. Isso é o produto — e é o risco. Quatro garantias estruturais, todas verificadas por teste automatizado:

1. **Escuta só em `127.0.0.1`.** Validado no código, não na configuração. Não existe flag para expor na rede.
2. **Nenhum comando vem do cliente.** A interface envia identificadores de ação (`docker.up`); a tradução para argv é tabela fixa no código. Não existe `/execute-command`. Execução sempre sem shell, com argv em lista.
3. **Todo path é validado** contra uma allowlist de diretórios raiz, com resolução de symlink. A allowlist só é editável no disco, nunca pela API.
4. **`Host` e `Origin` validados** — é o que fecha DNS rebinding, o ataque que derrota a checagem ingênua de origem.

O modelo completo, com ameaças, defesas e testes obrigatórios, está em [`docs/07-security-model.md`](docs/07-security-model.md).

## Instalação

### Como aplicativo (sem Python instalado)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1 -Install
```

Gera `dist\DevCockpit` (~59 MB) e instala uma cópia em `%USERPROFILE%\DevCockpit`. A instalação troca só o programa: `data\`, `logs\` e `configs\` são preservados.

Abre em **janela própria** (WebView2, o motor do Edge que já vem no Windows 11): sem barra de endereço, sem abas, com ícone na barra de tarefas. Fechar a janela encerra o servidor. Sem WebView2, cai para o navegador em vez de falhar.

Na primeira execução ele cria `data\`, `logs\` e `configs\` ao lado do executável, aplica as migrações e escolhe a porta (8765, ou a próxima livre). Abre em ~1,5 s.

<details>
<summary>Atalho no Desktop com porta fixa</summary>

```powershell
$s = (New-Object -ComObject WScript.Shell).CreateShortcut("$env:USERPROFILE\Desktop\DevCockpit.lnk")
$s.TargetPath = "$env:USERPROFILE\DevCockpit\DevCockpit.exe"
$s.Arguments = '--port 8790'
$s.WorkingDirectory = "$env:USERPROFILE\DevCockpit"
$s.Save()
```

Opções: `--port 9000` fixa a porta, `--no-window` usa o navegador, `--no-browser` só sobe o servidor.
</details>

### Como repositório (desenvolvimento)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1      # cria venv, migra e sobe
powershell -ExecutionPolicy Bypass -File scripts\serve.ps1    # modo solto, sobrevive ao terminal
```

**Passo obrigatório antes do primeiro cadastro** — defina os diretórios permitidos:

```powershell
copy configs\roots.example.yml configs\roots.yml
```

Sem isso nenhum projeto pode ser cadastrado, por decisão de segurança (defesa D4).

## Primeiros passos

1. **Projects → Varrer diretório** — aponte sua pasta de projetos e importe em lote.
2. **Fixe os 3 ou 4 do momento** — eles vão para a barra lateral e são os únicos que o verificador acompanha em background.
3. **Dashboard** passa a responder: o que está no ar, o que tem alteração pendente, qual porta está em conflito.

Atalhos: `Ctrl+K` busca projeto, `Ctrl+B` recolhe a lateral, `g d` vai ao Dashboard, `g p` a Projects, `r` recarrega.

## Arquitetura

```
rota HTTP  →  serviço  →  repositório  →  SQLite
                 ↓
             adapter  →  CommandRunner  →  processo externo
```

```
app/
  api/routes/        rotas HTTP — não conhecem o sistema operacional
  core/              config, log, erros, validação de path, cache
  models/ schemas/   SQLAlchemy e Pydantic
  repositories/      acesso a dados, sem query espalhada
  services/          casos de uso
  runner/            CommandRunner — único ponto de execução
  jobs/              execução assíncrona com console via SSE
  detection/         registry extensível de detectores de stack
  adapters/          git · docker · system
  launcher.py        ponto de entrada do aplicativo empacotado
frontend/            HTML, CSS e ES modules — sem build, sem dependência
migrations/ configs/ docs/ tests/ scripts/
```

| Camada | Tecnologia |
|--------|-----------|
| Backend | Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy, Alembic |
| Banco | SQLite (WAL) |
| Frontend | HTML, CSS e JavaScript — ES modules, **sem framework e sem build** |
| Empacotamento | PyInstaller + pywebview (WebView2) |
| Externo | `git` CLI, `docker compose` v2 CLI |

Cada escolha tem ADR em [`docs/adr/`](docs/adr/).

## Testes

```powershell
.venv\Scripts\python.exe -m pytest -q                              # tudo
.venv\Scripts\python.exe -m pytest -q --cov=app --cov-report=term  # com cobertura
.venv\Scripts\python.exe -m ruff check app tests
```

**496 testes**, cobertura **88%**. A suíte de frontend roda no runner do próprio Node (`node --test`), sem `node_modules`, e é chamada de dentro do `pytest` — comando único. Testes que exigem Docker estão marcados e não rodam por padrão.

Há testes que existem para proteger decisões, não código: um varre o fonte e reprova se `subprocess` for importado fora de `app/runner/`; outro garante que nenhum verbo destrutivo do Docker é alcançável por qualquer caminho da API.

## Documentação

| Doc | Conteúdo |
|-----|----------|
| [00 — Visão de produto](docs/00-product-vision.md) | problema, público, valor |
| [02 — Requisitos funcionais](docs/02-functional-requirements.md) | `FR-001` em diante |
| [04 — Arquitetura](docs/04-system-architecture.md) | camadas, fluxos, estrutura |
| [05 — Modelo de dados](docs/05-data-model.md) | entidades, campos, índices |
| [06 — API](docs/06-api-specification.md) | endpoints, payloads, erros |
| [07 — Segurança](docs/07-security-model.md) | ameaças, defesas, testes obrigatórios |
| [12 — Decisões](docs/12-decisions.md) | índice de ADRs e decisões menores |
| [ai/](docs/ai/) | proposta do **Cockpit AI** — 9 documentos, ainda não implementado |
| [logs/session-log.md](logs/session-log.md) | diário técnico: cada defeito, causa e conserto |

## Roadmap

- [x] Descoberta, detecção de stack e cadastro em lote
- [x] Git somente leitura, Docker Compose, health de serviços locais
- [x] Mapa de portas com prova de dono e resolução de conflito
- [x] Ligar/desligar ambiente, com Compose e servidor de dev
- [x] Análise histórica (atividade, disponibilidade, stack)
- [x] Aplicativo empacotado com janela nativa
- [ ] **Cockpit AI** — sessão, memória e contexto ([proposta](docs/ai/))
- [ ] Integração com GitHub (PRs, issues, Actions)

## Plataforma

Windows 11, por decisão ([ADR-007](docs/adr/ADR-007-os-abstraction-windows-first.md)): as ações de sistema operacional passam por um adapter, e portar para Linux/macOS é implementar esse adapter — o resto do código não conhece o sistema.

## O que ele não faz — por decisão

```
terminal web · editor de código · IDE embutida · CI/CD próprio
Kubernetes · execução remota · multiusuário · escrita destrutiva no Git
```

Não são "features futuras": exigiriam refazer o modelo de segurança inteiro.

---

<div align="center">
<sub>Projeto pessoal, desenvolvido com apoio de IA e documentado decisão a decisão.</sub>
</div>
