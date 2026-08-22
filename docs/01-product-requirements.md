# 01 — Product Requirements Document (PRD)

## Visão geral

DevCockpit é uma aplicação web local (FastAPI + HTML/CSS/JS) que inventaria os
projetos de desenvolvimento da máquina, expõe o estado operacional de cada um
(Git, Docker, serviços, portas) e executa um conjunto fechado de ações seguras
sobre eles.

## Problema

Ver `00-product-vision.md`. Resumo: o conhecimento operacional dos projetos
locais não é persistido em nenhum lugar consultável, e retomar um projeto
custa minutos de arqueologia manual.

## Objetivos

| # | Objetivo | Como se mede |
|---|----------|--------------|
| O1 | Inventário completo dos projetos locais | 100% dos projetos ativos do dev cadastrados |
| O2 | Retomada rápida | abrir VS Code + terminal + app de um projeto em < 30s |
| O3 | Visibilidade de pendências Git | dashboard mostra projetos com alteração sem commit |
| O4 | Operação Docker sem terminal | up/down/restart/logs pela interface |
| O5 | Zero execução arbitrária | nenhum endpoint aceita comando livre |

## Não objetivos

- substituir o terminal (o objetivo é reduzir uso, não eliminar)
- substituir o VS Code ou virar IDE
- gerenciar ambiente remoto ou de produção
- suportar múltiplos usuários ou perfis de permissão
- ser um orquestrador (não competimos com Compose/K8s; nós os acionamos)

## Personas

**P1 — Dev solo com muitos projetos (principal).**
Mantém dezenas de repositórios locais em estágios diferentes. Alterna entre
eles com frequência. Dor central: contexto perdido.

**P2 — Dev aprendendo arquitetura (secundária).**
Usa o próprio DevCockpit como projeto de estudo. Consequência de produto: o
código precisa ser legível e documentado, não só funcional. Isso é requisito,
não bônus.

## Casos de uso

- **UC-01** Cadastrar um projeto informando o diretório local.
- **UC-02** Descobrir projetos automaticamente varrendo diretórios raiz.
- **UC-03** Ver o dashboard com o estado agregado do ambiente.
- **UC-04** Abrir a página de um projeto e ver Git, Docker e serviços.
- **UC-05** Abrir o projeto no VS Code.
- **UC-06** Abrir a pasta do projeto no explorador de arquivos.
- **UC-07** Abrir um terminal já posicionado na pasta do projeto.
- **UC-08** Subir os serviços Docker do projeto.
- **UC-09** Parar / reiniciar os serviços Docker do projeto.
- **UC-10** Acompanhar logs de um container.
- **UC-11** Abrir a URL local do app (localhost:porta).
- **UC-12** Consultar o histórico de ações executadas.

## Features do MVP

| ID | Feature | Módulo |
|----|---------|--------|
| F1 | CRUD de projetos + persistência SQLite | 2 |
| F2 | Detecção de stack por marcadores de arquivo | 3 |
| F3 | Descoberta de projetos por varredura de diretório | 2/3 |
| F4 | Leitura de estado Git (somente leitura) | 4 |
| F5 | Estado e controle Docker Compose | 5 |
| F6 | Health check de serviços com cache | 6 |
| F7 | Ações de SO: VS Code, pasta, terminal, browser | 7/8 |
| F8 | Dashboard agregado | 1 |
| F9 | Log de atividade / auditoria | 14 |
| F10 | Execução assíncrona de comandos longos (jobs) | — |

F10 não está no prompt original e é pré-requisito de F5. Ver
`ADR-006`.

## Critérios de sucesso

- o dev usa o DevCockpit como ponto de entrada diário em vez do Explorer
- `GET /api/dashboard` responde em < 500 ms com 30 projetos cadastrados
- nenhuma ação da interface consegue produzir um comando não previsto
- cobertura de testes >= 70% nas camadas `services/`, `runner/` e `detection/`

## Riscos

| Risco | Impacto | Mitigação |
|-------|---------|-----------|
| Superfície de ataque local (CSRF via browser) | Alto | bind 127.0.0.1, token de origem, ver `07` |
| Path traversal em ações de SO | Alto | allowlist de roots + canonicalização |
| Latência de varredura de disco | Médio | varredura assíncrona com profundidade limitada |
| Docker daemon indisponível | Médio | degradar para `UNKNOWN`, nunca falhar o dashboard |
| Diferença entre plataformas | Médio | `OSAdapter` por plataforma, ver `ADR-005` |
| Escopo inflar (IA, GitHub, deploy) | Alto | congelar MVP nas 10 features acima |

## Dependências externas

- `git` no PATH
- `docker` + plugin `compose` v2 no PATH (opcional; ausência degrada)
- `code` no PATH (opcional)
- Python 3.11+

## MVP

Fases 0 a 4 do roadmap. Fases 5 e 6 (GitHub, IA) ficam fora.

## Roadmap

Ver `09-development-roadmap.md`.
