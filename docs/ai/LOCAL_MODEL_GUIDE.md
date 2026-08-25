# Modelo local no DevCockpit — guia de uso

> **Status: implementado e em uso.** Escrito a partir de medições feitas nesta
> máquina em 2026-08-25, não de números de catálogo.

Este é o guia prático de como usar o Ollama dentro do painel: quando vale o
modelo rápido, quando vale o caprichado, e o que esperar de cada um. Os
documentos vizinhos explicam *como funciona por dentro* — este explica *como
usar*.

## O que está configurado

| | |
|---|---|
| Provedor | `local` — Ollama em `http://127.0.0.1:11434` |
| Modelo rápido | `qwen2.5-coder:3b` |
| Modelo caprichado | `qwen2.5-coder:7b` |
| Chave de API | nenhuma. Não existe e não é necessária |
| Custo em dinheiro | zero |

Com o provedor local, **nada sai do computador**. O modelo roda no seu
hardware, e o painel fala com ele em loopback — a mesma regra que o resto do
DevCockpit já segue (NFR-001).

Isso não dispensa o resto das defesas: arquivo de segredo continua sem ser
lido, e chave que apareça em código continua saindo como `[REDIGIDO]`
(`AI_SECURITY.md`, defesa D-A2). O provedor mudou; a disciplina, não.

## Antes de tudo: o Ollama precisa estar no ar

O painel não sobe o Ollama. Se ele estiver fechado, a resposta é:

> O Ollama não respondeu em http://127.0.0.1:11434. Abra o aplicativo Ollama,
> ou rode `ollama serve` num terminal.

Deixar o aplicativo Ollama abrir junto com o Windows resolve isso de uma vez.

## Os dois caminhos

O painel tem dois lugares para perguntar, e a diferença entre eles **não é
visual — é o que vai na requisição**.

### Pergunta rápida — `Ctrl+Espaço`

Para dúvida de terminal, Git, Docker, Python, Node, Windows. Também no botão de
terminal na barra superior, alcançável de qualquer tela.

- **não manda contexto de projeto nenhum** — só a pergunta;
- não é guardada em lugar nenhum;
- o gasto de tokens é contabilizado no teto do dia.

Não ser persistida é decisão de esquema, não descuido: a mensagem pende de uma
sessão, que pende de um projeto. Guardar "como desfaço um commit?" no histórico
de um projeto qualquer sujaria o registro que existe para responder "o que eu
fiz aqui?".

### Chat de projeto — Projeto → aba **IA**

Para pergunta *sobre um projeto*. O painel manda junto a identidade do projeto,
a memória, a sessão em andamento, as tarefas abertas e o README.

É o caminho certo para "o que ficou pendente aqui?" e o caminho errado para
"qual o comando do `netstat`?".

## Quando usar o caprichado

**Regra: o 3b responde sempre. O 7b é a segunda tentativa.**

Na pergunta rápida, depois da resposta aparece **"Refazer com o caprichado"** —
um clique, mesma pergunta, modelo maior. No chat de projeto, o seletor
**Rápido | Caprichado** fica no cabeçalho e é escolhido antes de perguntar.

Por que não um roteador automático que decide sozinho: para julgar "essa
pergunta é difícil" seria preciso um modelo, e aí se paga uma chamada inteira
só para escolher quem responde — num provedor onde uma chamada custa dezenas de
segundos. Quem julga se a resposta serviu é você, olhando para ela. O custo
disso é zero quando o 3b acerta, e ele acerta na maioria.

## Os números desta máquina

Medidos com quatro perguntas reais de terminal (porta ocupada, desfazer commit,
erro do Compose, ativar `.venv`), e com uma pergunta carregando ~2.700 tokens
de contexto de projeto.

| Modelo | Pergunta de terminal | Com contexto de projeto |
|--------|---------------------|-------------------------|
| `qwen2.5-coder:3b` | 16,8 s (média) | 45,0 s |
| `qwen2.5-coder:7b` | 32,5 s (média) | 88,4 s |

O 7b custa aproximadamente o dobro em toda parte.

### O gargalo é ler, não gerar

| Modelo | Ler o contexto | Gerar a resposta |
|--------|---------------|------------------|
| `qwen2.5-coder:3b` | 74,3 tokens/s | 10,8 tokens/s |
| `qwen2.5-coder:7b` | 33,6 tokens/s | 5,1 tokens/s |

Parece contraditório — ler é mais rápido por token — mas o contexto tem
milhares de tokens e a resposta tem dezenas. Ler 2.700 tokens custou 36,7 s no
3b e 81,1 s no 7b; gerar 38 tokens custou 3,5 s e 7,1 s.

**É por isso que a pergunta rápida existe.** Ela não é uma tela a mais: é o
caminho que não paga o custo de ler contexto que não tem relação com a
pergunta.

### Por que a máquina é o limite

Esta máquina não tem GPU utilizável pelo Ollama — a Intel UHD 730 não é aceita,
então tudo roda em CPU (6 núcleos físicos). Com uma placa dedicada, os números
acima mudam de ordem de grandeza. Sem ela, são o teto.

## Por que o qwen, e não o llama

As mesmas quatro perguntas de terminal, nos dois modelos de 3B:

| Pergunta | `llama3.2:3b` | `qwen2.5-coder:3b` |
|----------|--------------|-------------------|
| PID de quem ocupa a porta | inventou um `tasklist \| where {…}` que não funciona | correto, com `/F` |
| desfazer commit sem push | **errado** — `git reset --soft` sem `HEAD~1` não faz nada | **correto** |
| `port is already allocated` | correto | correto, mais completo |
| ativar `.venv` no PowerShell | **errado** — `.\venv` em vez de `.\.venv`, e `source .venv/bin/activate` no Windows | **correto** |

O llama errou três das quatro, e ainda foi mais lento na média (22,8 s contra
16,8 s). Um modelo treinado em código ganha de um modelo generalista do mesmo
tamanho quando as perguntas são de código — o que é o esperado, mas convém ter
medido em vez de supor.

## O aviso que importa

Um modelo de 3B **erra**. O de 7B erra menos, e também erra.

No terminal, comando errado custa trabalho: o próprio llama sugeriu
`git reset --hard` como se fosse alternativa inofensiva ao `--soft`. Use o
modelo local como memória auxiliar — antes de rodar qualquer coisa que
**apaga arquivo, descarta alteração ou encerra processo**, confira.

O prompt do assistente de terminal já pede que ele avise sobre comando
destrutivo antes de mostrá-lo. Pedir não é garantir.

## Configuração

O arquivo é o `.env`, e o lugar dele depende de como você roda o painel:

| Como você roda | Onde o `.env` fica |
|----------------|-------------------|
| Aplicativo empacotado | ao lado do `DevCockpit.exe` — a mesma pasta de `data/`, `logs/` e `configs/` |
| Pelo código | raiz do repositório |

Variável já definida no ambiente do sistema ganha do arquivo.

```ini
DEVCOCKPIT_AI_ENABLED=true
DEVCOCKPIT_AI_PROVIDER=local
DEVCOCKPIT_AI_MODEL=qwen2.5-coder:3b
DEVCOCKPIT_AI_MODEL_ALT=qwen2.5-coder:7b
DEVCOCKPIT_AI_BASE_URL=http://127.0.0.1:11434

# Modelo local carrega na memória na primeira pergunta do dia.
DEVCOCKPIT_AI_TIMEOUT=180

# Ajustado ao ritmo medido acima: 12.000 tokens custariam ~2,5 min só de
# leitura no 3b, antes da primeira palavra da resposta.
DEVCOCKPIT_AI_MAX_CONTEXT_TOKENS=4000
```

`DEVCOCKPIT_AI_MODEL_ALT` vazio desliga a escolha, e o seletor nem aparece na
tela — oferecer escolha entre uma opção só é ruído.

**Ligar a IA é ato fora da interface, de propósito** (defesa D-A1). Nenhuma
tela do painel edita essas variáveis: a API não amplia a si mesma.

Depois de editar, feche e abra o DevCockpit.

## Trocar de modelo

O nome tem que ser **exatamente** o que `ollama list` mostra, com a etiqueta.
Errar o nome dá um erro que já lista o que está instalado:

> O modelo 'llama3.1' não está instalado no Ollama. Instalados: llama3.2:1b,
> llama3.2:3b. Escolha um em `DEVCOCKPIT_AI_MODEL`, ou baixe o que falta com
> `ollama pull llama3.1`.

Para adicionar um modelo:

```powershell
ollama pull <nome>
```

Depois é só apontar `DEVCOCKPIT_AI_MODEL` ou `DEVCOCKPIT_AI_MODEL_ALT` para
ele e reabrir o painel.

## Memória

Os dois modelos carregados ao mesmo tempo ocupam ~7,3 GB de RAM. O Ollama
descarrega sozinho depois de alguns minutos sem uso, mas alternar rápido entre
rápido e caprichado força recarga — que é o pior caso de latência.

Se a máquina estiver apertada, `ollama ps` mostra o que está carregado agora.

## Erros e o que significam

| O que aparece | O que houve | O que fazer |
|---------------|-------------|-------------|
| "O Ollama não respondeu em …" | Ollama fechado | abrir o aplicativo, ou `ollama serve` |
| "O modelo … não está instalado" | nome errado ou modelo não baixado | usar um dos listados na mensagem, ou `ollama pull` |
| "O Ollama conectou mas não respondeu a tempo" | modelo carregando na memória, ou máquina ocupada | aumentar `DEVCOCKPIT_AI_TIMEOUT`, ou usar o modelo menor |
| "O Cockpit AI está desligado" | `DEVCOCKPIT_AI_ENABLED` não é `true` | editar o `.env` e reabrir o painel |
| "O orçamento de tokens do dia acabou" | teto diário atingido | `DEVCOCKPIT_AI_DAILY_TOKEN_BUDGET` — com provedor local não há custo em dinheiro, só medida de uso |

## O que este guia não cobre

- **Orquestração de especialistas** (revisor, depurador, planejador) e comandos
  `/` — é a Fase 3, ainda não implementada. Ver `AGENT_ORCHESTRATION.md` e
  `AI_IMPLEMENTATION_PLAN.md`.
- **A IA executar ações** — ela não executa nada hoje, e quando executar será
  por identificador de ação já existente, com confirmação (defesa D-A3).
- **Provedores de nuvem** — o desenho aceita `anthropic` e `openai` pelas mesmas
  variáveis; o que muda é que aí passa a haver chave, custo e dado saindo da
  máquina.

## Uma restrição a considerar na Fase 3

Com 6 núcleos e sem GPU, **agentes em paralelo não vão acontecer** aqui. Um
orquestrador que dispare três especialistas ao mesmo tempo vai somar as
esperas, não dividi-las. O desenho que cabe nesta máquina é sequencial e curto.
