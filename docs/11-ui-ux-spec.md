# 11 — Especificação de UI/UX e Design System

## Princípio de interface

O DevCockpit é uma ferramenta de consulta rápida, não um lugar onde se passa o
dia. A tela boa é a que responde a pergunta em menos de dois segundos e sai da
frente.

Três regras derivadas:

1. **Estado antes de ação.** Primeiro o usuário entende o que está acontecendo;
   os botões vêm depois, no contexto.
2. **Nunca mentir sobre frescor do dado.** Se veio de cache de 40 segundos
   atrás, a tela diz. Dado velho apresentado como tempo real destrói a
   confiança na ferramenta.
3. **Ação impossível aparece desabilitada com o motivo.** `code` fora do PATH
   não deve produzir clique que falha; deve produzir botão apagado dizendo por
   quê.

## Referências

GitHub, Linear, Vercel, Railway, Docker Desktop, Portainer, VS Code — usados
como referência de **organização e densidade de informação**, nunca de layout
copiado. O que se aproveita:

| Fonte | O que se aproveita |
|-------|--------------------|
| Linear | densidade alta sem poluição; teclado em primeiro lugar |
| Vercel | hierarquia clara de status por cor |
| Docker Desktop | tabela de containers com ação inline |
| VS Code | sidebar fixa e tema escuro como padrão |
| GitHub | apresentação de estado de repositório |

## Layout

```
┌──────────┬────────────────┬───────────────────────────────────┐
│          │ Ativos      3  │ Topbar: busca (Ctrl+K) · trilho ·  │
│ Sidebar  ├────────────────┤         tema                      │
│ 216px    │ ● Dashdate     ├───────────────────────────────────┤
│ (56px    │   1/2 online   │                                   │
│ recolhida)│  [Ligado]     │  Área de conteúdo                 │
│          │                │                                   │
│ Dashboard│ ● ZapBot       │                                   │
│ Projects │   2/2 online   │                                   │
│ Ports    │   [Ligado]     │                                   │
│ Activity │                │                                   │
│ Settings │ FIXADOS        │                                   │
│          │ ○ KitEasy      │                                   │
│ ── ── ── │   [Desligado]  │                                   │
│ Pinned   │                │                                   │
└──────────┴────────────────┴───────────────────────────────────┘
```

Três colunas, e as duas primeiras recolhem. O estado de cada uma mora no
`localStorage` (`devcockpit:sidebar`, `devcockpit:rail`), pelo mesmo motivo do
tema: é preferência de quem olha a tela naquele monitor.

**Sidebar recolhida** (`Ctrl+B`) some com o texto e deixa o ícone. Cada item
mantém `title` e `aria-label`, e as seções que só existem como texto — fixados
e ferramentas — saem inteiras em vez de virar ícone sem legenda.

**Trilho de projetos** responde "o que está de pé agora?" sem tirar ninguém da
tela em que está. Lê o mesmo cache agregado do dashboard: um painel sempre
visível não pode disparar verificação por projeto (NFR-010/NFR-011). Abaixo de
1100px ele sai de cena — nessa largura ele e o conteúdo disputam o mesmo espaço,
e quem perde é o conteúdo.

Projetos fixados na sidebar é adição ao esboço do prompt: com dezenas de
projetos, "os 4 que eu uso hoje" precisam de acesso em um clique.

## Design tokens

Tema escuro é o padrão. Claro vem depois, e por isso tudo é token desde o
início — nenhuma cor literal em componente.

```css
:root {
  /* superfícies */
  --bg-base:      #0e1116;
  --bg-surface:   #161b22;
  --bg-elevated:  #1c2230;
  --bg-hover:     #21262d;
  --border:       #2d333b;
  --border-strong:#404650;

  /* texto */
  --fg-primary:   #e6edf3;
  --fg-secondary: #9198a1;
  --fg-muted:     #656c76;

  /* semânticas de status */
  --status-running: #3fb950;
  --status-stopped: #6e7681;
  --status-error:   #f85149;
  --status-warning: #d29922;
  --status-starting:#58a6ff;
  --status-unknown: #8957e5;

  --accent:       #2f81f7;
  --accent-hover: #4493f8;

  /* espaçamento — escala de 4 */
  --sp-1: 4px;  --sp-2: 8px;  --sp-3: 12px; --sp-4: 16px;
  --sp-5: 24px; --sp-6: 32px; --sp-7: 48px;

  --radius-sm: 4px; --radius-md: 6px; --radius-lg: 10px;

  --font-ui:   ui-sans-serif, "Segoe UI", system-ui, sans-serif;
  --font-mono: "Cascadia Code", ui-monospace, Consolas, monospace;

  --fs-xs: 11px; --fs-sm: 12px; --fs-md: 14px;
  --fs-lg: 16px; --fs-xl: 20px; --fs-2xl: 28px;

  --shadow-md: 0 4px 12px rgba(0,0,0,.35);
  --dur-fast: 120ms; --dur-med: 200ms;
}
```

Path, porta, hash de commit, nome de container e log usam sempre
`--font-mono`. É informação que se copia e se compara caractere a caractere.

## Estados de status

Vocabulário único em toda a aplicação. Cor **nunca** é o único sinal — sempre
acompanha rótulo.

| Estado | Cor | Rótulo | Significado |
|--------|-----|--------|-------------|
| `RUNNING` | verde | Running | serviços respondendo |
| `STOPPED` | cinza | Stopped | nada rodando; normal |
| `STARTING` | azul | Starting | operação em curso |
| `ERROR` | vermelho | Error | falhou |
| `UNKNOWN` | roxo | Unknown | não foi possível saber (daemon fora do ar) |
| `MISSING` | vermelho contornado | Missing | diretório não existe mais |
| `STALE` | cinza + relógio | Stale | dado antigo, reverificação pendente |

`UNKNOWN` distinto de `ERROR` é essencial: "não sei" e "está quebrado" levam a
ações diferentes.

## Componentes

| Componente | Uso |
|------------|-----|
| `StatCard` | número grande + rótulo + delta; usado no dashboard |
| `ProjectCard` | nome, path em mono, chips de stack, badge de status, badge Git, chave liga/desliga, ações rápidas |
| `RailCard` | versão condensada do `ProjectCard` para o trilho: ponto de estado, nome, `x/y online`, chave liga/desliga |
| `PowerToggle` | chave de estado do projeto: mostra ligado/desligado/em operação e age no clique |
| `StatusBadge` | ponto colorido + rótulo |
| `TechChip` | tecnologia detectada; contorno quando `MANUAL` |
| `ContainerRow` | serviço, estado, imagem, portas, uptime, ações inline |
| `ServiceRow` | rótulo, URL clicável em mono, latência, estado |
| `GitPanel` | branch, ahead/behind, contagens, arquivos, último commit |
| `ActionBar` | grupo de ações da página do projeto |
| `JobConsole` | saída mono com autoscroll, estado e tempo decorrido |
| `LogViewer` | logs de container, com filtro e pausa de autoscroll |
| `EmptyState` | ícone, frase e ação primária |
| `Toast` | confirmação e erro, com `correlation_id` copiável |
| `ConfirmDialog` | ação de impacto; exige confirmação explícita |
| `DataFreshness` | "atualizado 12s atrás" + botão de recarregar |

`DataFreshness` não estava no esboço e é consequência direta da regra 2.

## Telas

### Dashboard

```
Ambiente de desenvolvimento              atualizado 8s atrás  [↻]

┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
│  27    │ │   3    │ │   14   │ │   7    │ │   9    │
│Projetos│ │Rodando │ │c/Docker│ │Contain.│ │c/ Git  │
└────────┘ └────────┘ └────────┘ └────────┘ └────────┘

⚠ Porta 8000 usada por 2 projetos: dashdate, marketlab

Alterações pendentes            Serviços ativos
KitEasy      main    5 arq.     SmartDash  Backend  :8123  ●
ZapBot       main    2 arq.     ZapBot     API      :8080  ●
MarketLab    dev     1 arq.     KitEasy    Frontend :3000  ●

Acessados recentemente
SmartDash · KitEasy · Dashdate · MarketLab
```

Conflito de porta em destaque no topo: é a dor que aparece na hora errada, e
antecipá-la é o ganho mais barato de DX da tela.

### Projects

Lista ou grade, com busca, filtro por stack/status/Docker, ordenação por último
acesso. Ações rápidas no card sem abrir o projeto: VS Code, pasta, terminal,
subir/parar.

Estado vazio: "Nenhum projeto ainda" com dois caminhos — **Adicionar pasta** e
**Varrer diretório**. O segundo é o atalho que carrega 20 projetos de uma vez.

### Página do projeto

```
← Projetos

Dashboard Contábil                            ● Running
C:/Users/User/Projetos/dashboard-contabil            📌

[VS Code] [Pasta] [Terminal] [Abrir App] [Parar] [Reiniciar]

Overview | Git | Docker | Services | Activity | Settings
─────────────────────────────────────────────────────────
Stack        python · fastapi · postgresql · docker
Git          main · 3 alterações · há 2h
Docker       3 de 3 containers rodando
Services     2 online · 1 offline
```

Abas evitam a página gigante que rola sem fim. Overview responde a pergunta
mais comum sem clique adicional.

### Ports

Uma tela para o conflito que aparece sozinho com dezenas de projetos locais:
todo mundo quer 3000, 5173 e 8000. Lista as portas **declaradas** no registro,
marca as que mais de um serviço reivindica e troca o número na própria linha —
com sugestão da primeira porta livre.

O que ela edita é a porta do registro do DevCockpit: o que ele verifica e o que
ele abre. Não reescreve `.env`, Compose nem `vite.config` — arquivo do projeto é
do projeto. A tela diz isso na cara, e o toast repete depois de salvar, para
ninguém trocar aqui e achar que o servidor mudou de porta sozinho.

### Docker

Tabela de containers com ação por linha, botões de Compose no topo, console de
job aparecendo abaixo durante a operação — em painel próprio, não em modal.
Modal esconde justamente o que se quer acompanhar.

Daemon fora do ar: painel `UNKNOWN` com "Docker não está respondendo" e botão
de reverificar. Não é toast de erro: é estado da tela.

## Interação

| Ação | Comportamento |
|------|---------------|
| Ação longa | botão vira `Starting…` e desabilita; console de job abre |
| Erro | toast com mensagem de domínio + `correlation_id` copiável |
| Ferramenta ausente | botão desabilitado com tooltip explicando |
| Dado de cache | `DataFreshness` visível; recarregar força reverificação |
| Projeto `MISSING` | card com contorno vermelho e ações desabilitadas, exceto remover |
| Navegação | roteador por hash; recarregar mantém a tela |

### Atalhos de teclado

| Atalho | Ação |
|--------|------|
| `Ctrl+K` | busca de projeto |
| `Ctrl+B` | recolhe ou expande a barra lateral |
| `g d` | Dashboard |
| `g p` | Projects |
| `Esc` | fecha painel ou diálogo |
| `r` | recarrega dados da tela |

Teclado é DX central: a ferramenta serve para quem já vive no teclado.

## Acessibilidade

- contraste mínimo AA para texto (4.5:1)
- status sempre com rótulo textual, nunca só cor
- foco visível em todo elemento interativo
- ação de ícone com `aria-label`
- `aria-live` para conclusão de job
- navegação completa por `Tab`

## Frontend sem framework

`ES modules` servidos direto, sem build (NFR-071).

| Peça | Responsabilidade |
|------|------------------|
| `main.js` | inicializa, monta shell |
| `router.js` | rota por hash |
| `lib/api.js` | `fetch` com cabeçalho de cliente e tradução de erro |
| `lib/store.js` | estado observável mínimo |
| `lib/dom.js` | helpers de criação de elemento (sem `innerHTML` com dado dinâmico) |
| `lib/format.js` | tempo relativo, bytes, uptime |
| `pages/*.js` | uma página por arquivo, exporta `render(container, params)` |

Proibido no frontend: `innerHTML` com dado vindo da API (XSS via nome de branch
ou log de container é real), dependência via CDN, framework.
