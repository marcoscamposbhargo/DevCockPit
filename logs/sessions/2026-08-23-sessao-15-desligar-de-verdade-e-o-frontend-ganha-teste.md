## 2026-08-23 (fim de tarde) — Sessão 15: desligar de verdade, e o frontend ganha teste

Você escolheu três frentes e, no meio, cortou uma: o dashboard fica como está.
Sobraram ligar/desligar e teste de frontend.

### O "não desliga" que sobrou

Com o dashboard já corrigido para não inventar projetos no ar, restava o caso
real: **servidor deste projeto iniciado fora do painel**. `servers.status()` só
conhece o que nasceu daqui — a tabela `dev_server` —, então um `npm run dev`
iniciado no terminal deixava o botão sem alvo. Ele respondia sucesso e o
processo seguia atendendo.

`EnvironmentService.down` passou a olhar a última varredura de portas e encerrar
os processos que a descoberta classificou como **não gerenciados deste
projeto**. Quem valida é a descoberta, com a defesa D4 de sempre: só processo
dentro de um root permitido, e só o que ela mesma classificou — o PID não vem do
cliente. O desfecho novo é `stopped: "external"`, e a mensagem diz o que
aconteceu: "parei o servidor que estava rodando fora do painel".

Junto foi outro detalhe que incomodava: com Shift (derrubar tudo), a aplicação
local não parava — só os containers. Agora para as duas coisas.

### Teste de frontend: de zero a existir

Era o maior buraco do projeto: ~5.500 linhas de JavaScript, zero teste, e os
defeitos de interface sendo a maioria dos achados de toda sessão.

A escolha foi manter a doutrina do ADR-005 — o frontend não tem build nem
`node_modules`. Nada de jsdom: `tests/frontend/dom.mjs` é um DOM mínimo escrito
à mão, com o que os módulos realmente usam (`createElement`, `dataset`,
eventos, `append`), mais um relógio falso que conta timers armados. O runner é o
do próprio Node (`node --test`).

Dez testes, cobrindo exatamente o que quebrou hoje:

* o roteador limpa o que a tela deixou de pé ao trocar de rota — o bug do timer
  de Ports redesenhando por cima do Dashboard;
* limpeza roda uma vez só, e uma que falha não impede a próxima tela;
* o dashboard mostra no máximo sete portas, conflito primeiro;
* dia sem atividade continua na grade do gráfico.

`tests/unit/test_frontend_suite.py` roda a suíte de dentro do `pytest`, para o
comando único continuar sendo `pytest -q`. Sem Node instalado ela é **pulada**,
não falha.

Total: 496 testes.

### Continua com você

- [ ] testar o "Desligar" num projeto que você subiu pelo terminal: deve dizer
      que parou o servidor de fora do painel
- [ ] a suíte de frontend cobre roteador e dashboard; Ports, projects e o
      painel de análise ainda não têm teste
- [ ] `Dockerfile`, `docker-compose.yml` e `.dockerignore` untracked na raiz
- [ ] a branch `varredura/bugs-e-organizacao` acumula commits fora da `main`

---

