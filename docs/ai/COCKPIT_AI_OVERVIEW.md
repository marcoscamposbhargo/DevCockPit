# Cockpit AI — Visão geral

> Documento 1 de 9. Índice em [`README.md`](README.md) desta pasta.
> **Status: proposta.** Nada aqui está implementado.

## O que se quer

Transformar o DevCockpit de painel de operação em centro de comando com
contexto: abrir a ferramenta e ela já saber onde o trabalho parou, o que está
sendo construído e qual é o próximo passo.

## O que o DevCockpit é hoje

Um painel local que responde perguntas sobre **o estado da máquina agora**:

| Domínio | O que sabe | Onde vive |
|---------|-----------|-----------|
| Projetos | 28 cadastrados, caminho, stack detectada, status | `project`, `project_technology` |
| Serviços | porta declarada, estado ONLINE/OFFLINE, latência | `project_service`, `health_snapshot` |
| Portas | quem escuta, de quem é (com prova), conflitos | descoberta em memória + cache |
| Docker | containers, Compose, up/down/logs | adapter, sem persistência própria |
| Git | branch, sujeira, commits, remotes — **somente leitura** | cache |
| Execução | servidor de dev subido pelo painel | `dev_server` |
| Auditoria | toda ação executada, com desfecho e duração | `activity_log` |
| Análise | atividade por dia/hora/ação, uptime por serviço | `analytics_service` |

Três doutrinas o governam, e elas decidem o desenho de qualquer incremento:

1. **Nenhum comando vem do cliente** (ADR-003). A interface manda
   identificadores de ação (`docker.up`); a tradução para argv é tabela fixa no
   código. Não existe `/execute-command`.
2. **Todo path é validado** contra a allowlist de `configs/roots.yml`, que a
   API não edita (defesa D4, decisão D-10).
3. **Prova afirma, inferência sugere, ausência se cala.** O painel só diz "no
   ar" quando consegue provar de quem é o processo.

## O que o Cockpit AI acrescenta

Uma camada que responde perguntas sobre **a trajetória do trabalho**: o que foi
feito, por que foi decidido assim, o que falta, o que fazer agora.

```
        HOJE                          COM O COCKPIT AI
  "o que está no ar?"            "onde eu parei e por quê?"
  "que porta é essa?"            "qual o próximo passo?"
  "sobe esse projeto"            "o que decidimos sobre autenticação?"
```

## O buraco que precisa ser preenchido primeiro

O prompt de visão pressupõe uma camada de gestão — backlog, tarefas, roadmap,
sessões, documentação por projeto. **Nada disso existe no DevCockpit.** Não há
modelo de tarefa, de sessão nem de decisão.

Isso é a descoberta mais importante desta análise, e ela reordena tudo: sem
onde pendurar contexto, "memória de projeto" viraria um resumo que a IA escreve
sobre si mesma — texto gerado alimentando texto gerado. O antídoto é o mesmo
princípio da casa: **memória se ancora em fato observado**.

Fatos que o DevCockpit já tem e que a memória pode usar sem inventar nada:

- `activity_log` — o que foi executado, quando, com que desfecho;
- `health_snapshot` — o que esteve no ar e quando caiu;
- Git — commits, branch, arquivos sujos (leitura);
- detecção — stack real, lida do disco;
- `devcockpit.yml` — o que o projeto declara sobre si.

O que **não** existe e precisa ser criado: objetivo da sessão, decisões
tomadas, pendências, próximos passos. Isso é entrada humana ou síntese
aprovada por humano — nunca dedução silenciosa.

## Princípios do incremento

1. **Incremento, não sistema novo.** O Cockpit AI é um módulo dentro do
   `app/`, com as mesmas camadas (rota → serviço → repositório), a mesma
   auditoria e a mesma allowlist.
2. **A IA propõe, o painel executa.** O modelo nunca produz argv. Ele escolhe
   entre ações que já existem no registro, com parâmetros validados pelos
   mesmos validadores de hoje. Um modelo alucinando vira `403
   ACTION_NOT_ALLOWED` na auditoria, como qualquer cliente malformado.
3. **Nada sai da máquina sem consentimento explícito.** Hoje o DevCockpit é
   inteiramente local. Falar com um provedor de IA é mudança de natureza, não
   de funcionalidade: passa a existir dado do usuário trafegando para fora.
   Ver [`AI_SECURITY.md`](AI_SECURITY.md).
4. **Útil antes de sofisticado.** A primeira entrega precisa valer a abertura
   do dia mesmo se o modelo estiver desligado. Memória e sessão têm valor sem
   IA nenhuma; a IA só os torna mais rápidos de escrever e de consultar.
5. **Sem número inventado.** O Project Health Score só existe com critério
   mensurável por indicador. Onde não há medida, não há nota — a mesma regra
   que fez o painel parar de dizer "no ar" sem prova.

## Como se mede sucesso

| Pergunta | Hoje | Meta |
|----------|------|------|
| "Onde parei neste projeto?" | reler o código | resposta em uma tela |
| "O que fiz na semana?" | `git log` + memória | sessões registradas |
| "Por que decidimos assim?" | não existe registro | decisões consultáveis |
| Custo por sessão de IA | — | previsível e visível |
| Ação destrutiva feita pela IA sem confirmação | — | **zero, por construção** |

## Documentos

| Doc | Assunto |
|-----|---------|
| [ARCHITECTURE](COCKPIT_AI_ARCHITECTURE.md) | camadas, módulos, integração com o app atual |
| [CONTEXT_ENGINE](CONTEXT_ENGINE.md) | como o contexto é montado e limitado |
| [MEMORY_ARCHITECTURE](MEMORY_ARCHITECTURE.md) | os três níveis de memória |
| [AGENT_ORCHESTRATION](AGENT_ORCHESTRATION.md) | especialistas e roteamento |
| [AI_SECURITY](AI_SECURITY.md) | classificação de operações, segredos, dado que sai |
| [AI_DATABASE_SCHEMA](AI_DATABASE_SCHEMA.md) | tabelas novas e migrações |
| [AI_IMPLEMENTATION_PLAN](AI_IMPLEMENTATION_PLAN.md) | fases, entregas, critério de saída |
| [AI_ROADMAP](AI_ROADMAP.md) | ordem, dependências e o que fica fora |
