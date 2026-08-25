# Roadmap do Cockpit AI

> **Status: proposta.**

## Ordem e dependências

```
Fase 1  Fundação (sessão, memória, briefing)      ← não depende de IA
   ↓
Fase 2  Agente (provedor, contexto, chat)         ← depende de 1 (fatos)
   ↓
Fase 3  Especialistas, ações, tarefas             ← depende de 2
   ↓
Fase 4  Project Intelligence e Health Score       ← depende de 1 e 3
   ↓
Fase 5  Dados e automação                         ← depende de 2
```

A única dependência dura é **Fase 1 antes de Fase 2**: sem sessão e memória, o
agente não tem o que ler, e o "contexto" viraria resumo que a própria IA
escreveu — texto gerado alimentando texto gerado.

## O que entra em cada fase

| Fase | Entrega visível para o usuário |
|------|-------------------------------|
| 1 | ✅ "Iniciar sessão" e "Encerrar sessão" no projeto; Start My Day; memória editável |
| 2 | chat que já sabe de qual projeto se fala; resumo de sessão redigido; custo na tela |
| 3 | especialistas, comandos `/`, ações propostas com confirmação, tarefas |
| 4 | tela Project Intelligence com score explicável |
| 5 | análise de planilha e dataset; automações |

## O que fica fora, e por quê

| Item | Por quê |
|------|---------|
| A IA editar arquivo do projeto | quem edita é o VS Code / Claude Code; o Cockpit é comando, não editor (`00-product-vision.md`) |
| `git push`, merge, rebase pela IA | Git é somente leitura no painel desde a Fase 2 do produto; a IA não é motivo para abrir |
| Deploy automático | classe DESTRUCTIVE; fora do alcance |
| Agentes autônomos em laço | custo e modos de falha desproporcionais para um usuário só |
| Banco vetorial / embeddings | busca lexical resolve nesta escala; entra só se a qualidade cobrar |
| Multiusuário, IA compartilhada | contraria NFR-001 (loopback) e o modelo de segurança inteiro |

## Sinais de que a direção está errada

Vale escrever agora, com a cabeça fria, o que fará parar e repensar:

- **custo por sessão acima do previsto sem ganho percebido** — a ferramenta
  vira assinatura cara para escrever o que um `git log` resolveria;
- **o usuário parar de encerrar sessão** — significa que o registro não está
  valendo o esforço, e a memória vai apodrecer;
- **resposta do agente citando projeto errado** — falha do Context Engine; sem
  isso resolvido, nada acima vale;
- **primeira ação da IA executada sem confirmação** — falha de contenção; para
  tudo até ter teste que prove o contrário.

## Métricas

| Métrica | Meta inicial |
|---------|--------------|
| Sessões encerradas com resumo / sessões abertas | > 80% |
| Tokens de contexto por pergunta (p95) | < 12.000 |
| Custo por sessão | visível e previsível |
| Ações da IA executadas sem confirmação | **0** |
| Perguntas com contexto errado | < 5% |

## Depois

Se as cinco fases se pagarem, o passo natural não é mais IA: é **integração com
o fluxo de execução** — Cockpit define o objetivo, o VS Code abre já com o
contexto, o Claude Code recebe o mesmo contexto, e a sessão volta para o
Cockpit no fim. Isso é o item 17 do prompt de visão, e depende de decidir o
mecanismo (arquivo de contexto no projeto, protocolo local, extensão). Estudo
próprio, depois da Fase 3.
