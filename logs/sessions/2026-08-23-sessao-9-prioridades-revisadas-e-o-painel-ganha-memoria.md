## 2026-08-23 — Sessão 9: prioridades revisadas e o painel ganha memória

Duas coisas nesta sessão: reordenar o que estava pendente e atender ao pedido de
gráficos de análise no dashboard. As duas se encontraram num ponto só — a tabela
morta que o backlog mandava "implementar ou apagar" era exatamente a fonte de
dado que o gráfico pedido precisava.

### As prioridades

A ordem passou a ser por dano, não por esforço, e está no topo do
`PROJECT_STATUS.md`: gráficos (P0), retenção (P1), higiene de repositório (P2),
as duas verificações manuais pendentes desde 21/08 (P3), teste de frontend e
`git_service` (P4), o serviço `db` do SmartDash (P5).

### `health_snapshot` deixa de ser schema sem escrita

A tabela existia desde a Fase 4. O poller media a cada 30 s e **jogava fora**. O
painel respondia "agora" e nunca "e antes?".

A política de escrita não é gravar tudo nem gravar só mudança:

* mudança de estado grava sempre — o minuto da queda vale mais que as duas horas
  de pé que vieram antes;
* sem mudança, grava a cada cinco minutos. Sem isso, uma semana estável teria um
  ponto só, e o gráfico não distinguiria "de pé o tempo todo" de "ninguém olhou".

Gravar todo ciclo seriam 2.880 linhas por serviço por dia para repetir a mesma
informação 2.879 vezes.

### Disponibilidade ponderada por tempo, e cobertura declarada junto

Histórico de health é **amostragem**, não registro de fato. Contar amostras
online sobre o total daria a três amostras o mesmo peso de um dia inteiro
medido. O uptime é ponderado pelo tempo que cada amostra cobre, com teto de dez
minutos por amostra: o que passa disso vira buraco de cobertura, não
disponibilidade.

Por isso `coverage_pct` viaja junto do número, e a tela deixa de colorir a barra
quando a cobertura é menor que 5% do período — 0% em vermelho a partir de dez
minutos medidos numa janela de duas semanas acusaria uma queda que ninguém
observou. É a regra da sessão 8 aplicada a um dado novo: prova afirma, amostra
rala sugere, ausência se cala.

### O defeito que só apareceu com dado real

Rodando contra a máquina, as primeiras amostras gravadas traziam
`latency_ms: 2657` em serviços `OFFLINE`. Não era latência do serviço: era o
tempo até o verificador desistir. Entrando na série, a latência "pioraria"
justamente quando o serviço caísse — o gráfico mediria a paciência do
verificador. Agora só amostra `ONLINE` alimenta latência e percentil.

### Retenção, enfim

`activity_retention_days` estava configurado desde a Fase 0 e nunca era lido: o
log de auditoria crescia sem limite num banco que mora na máquina do usuário.
Com o histórico de health passando a escrever, seriam duas tabelas assim. A poda
roda dentro do poller, de hora em hora, com retenção separada por tabela.

`timeout_scan` era a terceira configuração decorativa. Virou teto do job de
varredura: `submit_callable` aceita `timeout_s`, e o job que estoura termina
como `TIMEOUT` liberando a chave — antes ficaria `RUNNING` para sempre,
recusando toda varredura seguinte com 409 até o servidor reiniciar.

### Os gráficos

Cinco painéis no fim do dashboard, carregando por conta própria depois da tela
(o orçamento de 500 ms é do dashboard, não do histórico):

* **Atividade** — colunas empilhadas por dia, divididas por desfecho, com dias
  vazios presentes: omitir dia parado emendaria uma sexta-feira silenciosa na
  segunda seguinte;
* **Disponibilidade** — uptime por serviço, latência ao longo do tempo com os
  buracos preservados, p95;
* **Ações mais executadas** — volume, taxa de erro e p50/p95 de duração. A taxa
  vem ao lado do volume que a sustenta: 100% de erro em uma execução é anedota;
* **Horário de trabalho** — 24 células, uma por hora;
* **Stack dos projetos** — tecnologias por número de projetos.

Sem biblioteca de gráfico, como o resto do painel: SVG e HTML à mão, cores do
tema. `charts.js` ganhou `stackedColumns`, `lineSeries` (escala própria e
`null` que interrompe a linha) e `hourStrip`.

### Verificação

475 testes passando (19 novos), cobertura 89%, `ruff check` limpo. Os gráficos
foram renderizados fora do browser contra a API real, com um DOM mínimo, para
provar que os cinco painéis montam com dado de verdade — não substitui olhar a
tela, mas pega erro de execução antes de você abrir.

### Continua com você

- [ ] **Ctrl+F5** e olhar os gráficos: a aba aberta tem o JS antigo
- [ ] zero teste de frontend continua sendo o maior buraco, e acabou de crescer
      cinco painéis
- [ ] `git_service` a 47%, o menor do projeto
- [ ] `Dockerfile`, `docker-compose.yml` e `.dockerignore` untracked na raiz
- [ ] as três edições no SmartDash não commitadas
- [ ] a branch `varredura/bugs-e-organizacao` acumula commits fora da `main`
- [ ] clicar em VS Code e confirmar que a janela vem para frente (desde 21/08)
- [ ] conferir a aba Docker com o Docker Desktop desligado (desde 21/08)

---

