## 2026-08-27 (tarde) — Sessão 28: portas, e o painel gravando o impossível

Sessão que começou com "os atalhos funcionam?" e terminou em três defeitos de
porta. Nenhum deles era do que tinha acabado de ser entregue.

### O que foi testado de verdade

O pedido era honesto: os atalhos da Fase 3 tinham sido verificados só no nível
de rota e bilhete, com um único clique real (`git.status`, leitura). Executados
nesta sessão, com bilhete emitido pelo servidor:

| Atalho | Resultado |
|---|---|
| Subir o servidor (`server.start`) | `200`, pid 9404, porta respondendo, auditado com `actor=ai` |
| Ligar o ambiente (`environment.up`) | job `SUCCESS`: imagem construída, rede criada, container de pé, aplicação subida |

Os outros oito continuam verificados só no nível de rota — e isso está dito na
tela, não escondido.

### O primeiro defeito: conversar travava a escrita do painel

O clique em "Subir o servidor" devolveu "Erro interno". O log dizia
`database is locked` num INSERT em `dev_server`.

O repositório de mensagens só chama `flush()`, nunca `commit()`. A pergunta era
gravada **antes** do stream começar, e a transação de escrita ficava aberta até
o fim da requisição — com provedor local, minutos. O SQLite admite um escritor
por vez: nessa janela, qualquer outra escrita falhava. O poller de health caiu
junto, no mesmo segundo.

Conversar com a IA travava o painel inteiro para escrita enquanto ela respondia,
e o sintoma aparecia num botão sem relação nenhuma com o chat.

O conserto é `commit()` depois de gravar a pergunta e depois da resposta, mais
`PRAGMA busy_timeout=15000` como segunda linha. Verificado no painel real: com
uma resposta em stream, **seis escritas seguidas devolveram 200**.

**A lição do teste:** a primeira versão dele passava com e sem o conserto,
porque olhava `session.dirty` — que o `flush` já esvazia. Teste que passa dos
dois jeitos não é teste. A versão final consome o primeiro pedaço do stream e
exige que a sessão não esteja em transação; foi verificada nos dois sentidos.

### O segundo: a porta do Node escorregava

Levantado o mapa de portas dos 19 projetos, **nenhuma declaração colidia**. O
conflito nascia noutro lugar: em `resolve_run_plan`, Python, subprojeto e
estático recebiam a porta declarada, e `plan_from_node` **não**.

Sem porta no comando, `npm run dev` de um Next pega a 3000 e, se ela estiver
ocupada, escorrega para a 3001 — em silêncio. Dois projetos que não conflitam
no cadastro passam a disputar o mesmo número, o verificador mede a porta errada
e o diagnóstico vira adivinhação. Era o caso do SmartDash, que subia na 3001
declarando 3013.

Agora o Node recebe a porta e a fixa com a bandeira do framework: `-p` no Next,
`--port --strictPort` no Vite (sem `strictPort` ele também desliza), `--port` em
Astro, Nuxt e Remix. Duas recusas deliberadas: script que já fixa a porta não é
sobrescrito, e framework desconhecido fica como está.

**Erro meu, pego pelo próprio teste do diff:** a primeira versão de
`_declared_port` preferia `web` a `backend` pelo nome, e escolhia a porta 3017
(container) na PLATAFORMA DE INGRESSOS, onde quem sobe é o `runserver` da 3002.
Ordem é o que o projeto declarou; nome é o que o painel imagina. Ficou: pula
serviço TCP (para não mandar o Next subir na porta do Postgres) e, entre HTTPs,
respeita a ordem declarada.

Medido nos 19 projetos: **3 comandos Node mudam, nenhum Python.**

### O terceiro: o painel gravava estado impossível

A tela de Ports do AgilContabil mostrava três serviços declarados na **mesma
porta 3000**, com rótulos dizendo 5442 e 9010. Não era projeto mal configurado:

- `PUT /services` **não auditava** — a troca das três portas não estava no log,
  e "quem mudou isso?" não tinha resposta;
- **aceitava porta duplicada** no mesmo projeto, e a tela avisava depois sobre a
  inconsistência que o próprio painel gravou;
- **o rótulo não acompanhava a porta**: `App (5442)` numa linha cuja porta é
  3000 são dois números discordando, e o da esquerda é o que se lê primeiro.

Os três consertados. O rótulo com porta embutida é gerado pelo próprio painel ao
cadastrar uma porta observada, então só ele é reescrito — `Postgres` fica como
está.

O teste que criava a duplicata pela API passou a criá-la direto no banco: a tela
precisa continuar sabendo mostrar o caso, porque instalação antiga tem linhas
gravadas antes da regra.

### HyperBrain

O contexto do nó era uma coluna de 320px à direita, cobrando largura do grafo em
tempo integral para mostrar, quase sempre, o convite a selecionar um nó. Virou
faixa horizontal no topo: vazia ocupa uma linha, cheia deita o cartão.

Comparadas as duas telas lado a lado, com 19 projetos: antes os nós da direita
ficavam **cortados na borda**; agora cabem. A sobreposição entre nós vizinhos
existia antes e continua — é do layout, não da largura.

### Duas armadilhas de plataforma

**O banco efetivo não é o do repositório.** `alembic upgrade head` rodou e as
colunas não apareceram em `data/devcockpit.db`: o banco real é
`C:/Users/User/DevCockpit/data/devcockpit.db`, porque `settings.resolve`
reescreve o caminho relativo.

**Migração nova quebra o executável instalado.** O `.exe` carrega as migrações
empacotadas dentro dele; com o banco na 009 e o bundle na 008, o painel abre com
"Can't locate revision identified by '009_ai_especialista'". Migração nova =
reconstruir e reinstalar junto.

Na reinstalação, `VCRUNTIME140.dll` estava travada — desta vez pelo
`chrome-native-host.exe`, sem relação com o projeto. Hash idêntico ao novo, então
a saída foi copiar tudo menos ele (`robocopy /XF`) e conferir arquivo por arquivo
que nada faltou.

### Situação ao encerrar

Publicado até `fb2ab2a`, árvore limpa. 681 testes, 48 no frontend, ruff limpo.

O painel está no ar (PID 6112) com o **executável antigo**: as correções desta
tarde ainda não estão nele. Dois arquivos do HyperBrain (`hyperbrain.css` e
`hyperbrain.js`) foram copiados à mão para a instalação para ver o layout, então
a instalação está adiante do bundle nesses dois e atrás em todo o resto.

Containers de pé: `agilcontabil-postgres-1`, `agilcontabil-minio-1`, e
`eventos_api`/`eventos_db`, que não foram subidos por esta sessão. Os do kiteasy
foram derrubados com `docker compose down` depois do teste.

### Próximo passo

1. **Reconstruir e reinstalar** — é o que leva as três correções para o painel
   que você usa, e sincroniza os dois arquivos copiados à mão.
2. **Consertar os dados do AgilContabil**, que a regra nova impede piorar mas
   não desfaz: Postgres na 5442, MinIO em 9010/9011, e a porta real do backend —
   que segue em aberto, porque o comando detectado diz 3012 e o cadastro dizia
   3010. Decisão do usuário: rodar a detecção ou informar os números.

