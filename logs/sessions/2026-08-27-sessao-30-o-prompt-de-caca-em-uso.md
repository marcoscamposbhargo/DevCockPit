## 2026-08-27 (noite) — Sessão 30: o prompt de caça em uso

O prompt de caça de bugs foi escrito e imediatamente usado. Quatro defeitos,
todos do formato que ele nomeia, nenhum encontrado por acaso.

### Padrão 7 — correção que para na raiz (dois casos)

A busca profunda de Compose entrou na detecção e na aba Docker, e **duas outras
buscas continuaram só na raiz**:

- `environment_service._compose_file` — e aqui a consequência é pior que uma
  tela vazia: `plano.compose_file` ficava `None`, então **"Ligar o ambiente"
  subia a aplicação e pulava os containers**. No AgilContabil, isso é o app no
  ar sem Postgres nem MinIO, sem o painel dizer que faltou algo.
- `manifest_service._docker_section` — exportar um projeto com Compose em
  `infra/` produzia manifesto sem a seção `docker`.

### Padrão 3 — a terceira porta de entrada

A regra de porta única vivia dentro de uma função de rota. A tela recusava
duplicata, a detecção passou a pular, e a **importação de manifesto continuava
gravando**. Três caminhos para a mesma tabela, uma cópia da regra.

Agora ela mora em `app/services/portas.py`, e o manifesto valida o estado
**resultante** — não só o que ele traz: importar um serviço na porta de outro
que já existe grava a mesma duplicata.

### Padrão 6, aplicado a um lugar novo — o launcher

Porta ocupada tinha uma resposta só: pegar a próxima livre. Quando quem ocupa é
o **próprio** DevCockpit, isso sobe uma segunda instância — e duas instâncias
contra o mesmo SQLite disputam a escrita.

É a origem de um sintoma já visto: "database is locked" num botão sem relação
com o que estava sendo feito. E de outro, mais silencioso: depois de reconstruir
o executável, a janela aberta continua servindo o código velho, então um
conserto recém-instalado parece não ter funcionado. Isso aconteceu **nesta
sessão**, duas vezes, antes de eu perceber a causa.

O launcher agora pergunta quem está na porta, pela assinatura do `/api/health` —
não só por um `200`, porque qualquer servidor responde 200 e mandar a pessoa
para a tela de outro programa seria pior.

Verificado ao vivo: a segunda abertura respondeu "o DevCockpit já está aberto em
http://127.0.0.1:8765" e encerrou; uma instância, uma porta.

### Dois falsos positivos, descartados com evidência

- **site3d com `app_online=True`** parecia mentira. Não era: há um Next servindo
  de `C:\Users\User\Desktop\SITE3D` na 3006.
- **smartdash** sobe na 3001 declarando 3013. É dado do projeto, não defeito do
  painel — que já avisa, com a mensagem certa, no aviso de porta divergente.

### As três regras de "qual serviço é a aplicação"

Medidas nos 19 projetos, elas discordam em **um**: o smartdash, cujo backend
está cadastrado como TCP. Não vale unificar agora — o custo seria alto e o
ganho, um projeto com dado torto. Fica registrado como dívida conhecida:

| Onde | Regra |
|---|---|
| `dev_server_service._declared_port` | primeiro HTTP (pula TCP de propósito) |
| `environment_service._app_service_key` | primeiro com porta |
| `projects.py` (colore o grafo) | primeiro com `open_in_browser` |

### Situação ao encerrar

Publicado até `319780f`. 696 testes, 51 no frontend, ruff limpo. Painel
instalado igual ao build, uma instância na 8765.

### Próximo passo

O prompt tem sete padrões e a sessão usou quatro. Faltam varrer o **padrão 2**
(`null` virando `0`) fora do card de projeto, o **4** (ordem decidindo o que
deveria ser evidência) fora da detecção, e o **5** (transação longa) nas rotas
de job.

