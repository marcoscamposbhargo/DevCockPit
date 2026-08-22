# 00 — Product Vision

## Problema

O ambiente local de desenvolvimento de um dev que mantém muitos projetos ao
mesmo tempo é fragmentado. O conhecimento operacional de cada projeto — onde
ele está no disco, qual comando o sobe, qual porta usa, qual container
pertence a ele, se há alteração sem commit — não está em lugar nenhum. Está na
memória da pessoa, e envelhece rápido.

O custo disso não é o comando em si; é a **troca de contexto**. Retomar um
projeto parado por três semanas custa de 5 a 15 minutos de arqueologia:
abrir o Explorer, procurar a pasta, abrir o terminal, rodar `git status`,
descobrir que o Docker não está rodando, procurar a porta no `docker-compose.yml`,
descobrir que a porta está ocupada por outro projeto.

## Oportunidade

Toda essa informação é **derivável do próprio disco**. `requirements.txt`,
`package.json`, `docker-compose.yml`, `.git/HEAD` — o projeto já declara o que
ele é. Falta uma camada que leia isso, guarde o que não é derivável (a intenção
do dev) e ofereça as ações mais frequentes em um clique.

## Público

Desenvolvedor individual ou dupla, em máquina própria, mantendo entre 5 e 50
projetos locais heterogêneos (Python, Node, estáticos, com e sem Docker).

Não é público-alvo: time grande, ambiente compartilhado, servidor remoto,
operação de produção.

## Proposta de valor

Uma central local que responde, sem abrir terminal:

- quais projetos existem e onde estão
- o que está rodando agora
- o que tem alteração pendente no Git
- qual porta pertence a quem
- e que executa as ações seguras mais frequentes (abrir no VS Code, abrir
  pasta, abrir terminal na pasta, subir/parar Docker, ver logs, abrir o app)

## Contexto de execução

Aplicação **local**, single-user, servida em `127.0.0.1`. Não é um SaaS. Não há
multi-tenant. Isso é uma decisão de produto, não uma limitação temporária: o
valor vem justamente do acesso privilegiado à máquina do dev, e esse acesso
nunca deve estar exposto à rede.

## Objetivos

1. Reduzir o tempo de retomada de um projeto parado a menos de 30 segundos.
2. Tornar visível, em uma tela, o estado real do ambiente de desenvolvimento.
3. Nunca executar comando arbitrário vindo do frontend.
4. Funcionar em Windows como cidadão de primeira classe (é a máquina alvo),
   com arquitetura portável para Linux e macOS.

## Limitações iniciais (deliberadas)

- sem terminal web, sem editor web, sem IDE embutida
- sem execução remota, sem Kubernetes, sem CI/CD próprio
- sem autenticação (mitigado por bind local — ver `07-security-model.md`)
- sem escrita destrutiva no Git (nada de `reset`, `clean`, `push --force`)

## Visão de longo prazo

1. **Observabilidade** — histórico de atividade, uptime, portas em conflito.
2. **Integração GitHub** — PRs, issues, Actions por projeto.
3. **Dev Assistant** — diagnóstico assistido por IA sobre dados já coletados
   por serviços controlados, nunca com acesso livre ao sistema.

O ponto de chegada não é "um dashboard bonito". É a máquina de desenvolvimento
deixar de ser opaca.
