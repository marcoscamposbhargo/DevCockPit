// Liga/desliga de projeto, num controle só.
//
// Antes só existia dentro da aba Docker, em quatro botões soltos ("Subir",
// "Parar", "Reiniciar", "Derrubar") que não diziam em que estado o projeto
// está — o botão "Subir" tinha a mesma cara com tudo no ar e com tudo parado.
// Aqui o controle **mostra o estado** e a ação é a consequência dele.
//
// São dois controles, e a divisão é a do uso real:
//
// - **o botão** é a aplicação. Ligar sobe o ambiente e depois a aplicação, na
//   ordem; desligar para só a aplicação.
// - **o chip do Docker**, ao lado, é o ambiente. É por ele que se derruba os
//   containers, que é operação de fim de expediente e não de cada ciclo.
//
// A assimetria é deliberada. Banco e fila são caros de subir e não mudam entre
// uma execução e outra da aplicação: derrubá-los a cada parada do backend
// trocaria um ciclo de dois segundos por um de trinta. Mas o painel não pode
// dizer "Desligado" com o Postgres atendendo na porta — foi assim que o caso
// do ZAPBOT enganou —, então o chip existe para o ambiente ter voz própria.
//
// O que não dá para ligar continua desabilitado **com o motivo** na frente,
// nunca como um clique que falha depois (mesma regra de lib/actions.js).

import { api } from './api.js';
import { el } from './dom.js';
import { icon } from './icons.js';
import { showError, toast } from './ui.js';

const DOCKER_TECHS = new Set(['docker', 'docker-compose']);

//: Stacks para as quais existe um comando de subida derivável do próprio
//: projeto. Espelha o que `app/services/run_plan.py` sabe resolver — e é
//: heurística de propósito: perguntar ao servidor por projeto custaria uma
//: chamada por card, que é justamente o que NFR-010 proíbe na lista.
const RUN_TECHS = new Set([
  'node',
  'nextjs',
  'nuxt',
  'astro',
  'vite',
  'sveltekit',
  'express',
  'fastify',
  'nestjs',
  'fastapi',
  'starlette',
  'uvicorn',
  'flask',
  'django',
]);

const ESTADOS_FINAIS = new Set(['SUCCESS', 'FAILED', 'TIMEOUT', 'CANCELLED']);
const POLL_MS = 900;

/** Heurística barata: a stack detectada já diz se há Compose ou Dockerfile.
 *
 * Perguntar ao Docker por projeto custaria uma chamada por card — a lista de
 * projetos não pode disparar isso (NFR-010). */
export function hasDocker(project) {
  return temTech(project, DOCKER_TECHS);
}

/** O projeto parece ter servidor de desenvolvimento que o painel sabe subir. */
export function hasRunnableStack(project) {
  return temTech(project, RUN_TECHS);
}

function temTech(project, conjunto) {
  const techs = project.technologies ?? [];
  return techs.some((tech) => conjunto.has(typeof tech === 'string' ? tech : tech.name));
}

/** Espera um job terminar sem console: aqui o que importa é o desfecho. */
async function waitJob(jobId) {
  // `after` avança a cada volta: sem isso cada consulta rebaixaria a saída
  // inteira do `compose up` pela rede, e ninguém está lendo essa saída aqui.
  let entregues = 0;
  for (;;) {
    const job = await api.getJob(jobId, entregues);
    entregues = job.line_count ?? entregues;
    if (ESTADOS_FINAIS.has(job.status)) return job;
    await new Promise((resolve) => window.setTimeout(resolve, POLL_MS));
  }
}

//: Quanto tempo esperar a aplicação recém-subida começar a atender, e de
//: quanto em quanto perguntar. Oito segundos cobrem Vite e uvicorn com folga;
//: o que passar disso o verificador de background resolve sozinho.
const ESPERA_MAX_MS = 8000;
const ESPERA_PASSO_MS = 800;

/** Espera alguma porta declarada do projeto responder, com teto.
 *
 * Perguntar uma vez só devolveria "desligado" para algo que acabou de nascer:
 * entre o processo existir e o servidor atender há sempre alguns segundos, e o
 * botão voltaria sozinho para "Desligado" com o serviço subindo.
 */
async function esperarResposta(projectId) {
  const limite = Date.now() + ESPERA_MAX_MS;
  for (;;) {
    const { items } = await api.checkServices(projectId).catch(() => ({ items: [] }));
    if (items.some((item) => item.state === 'ONLINE')) return true;
    if (Date.now() >= limite) return false;
    await new Promise((resolve) => window.setTimeout(resolve, ESPERA_PASSO_MS));
  }
}

/** Sobe o ambiente inteiro: containers primeiro, aplicação depois.
 *
 * A sequência roda como job no servidor, porque `compose up` puxando imagem
 * leva minutos e uma requisição pendurada esse tempo é a forma errada de
 * esperar. Aqui só acompanhamos o desfecho.
 */
/** Explica o impedimento e pergunta o que fazer.
 *
 * Três saídas, e a ordem importa: encerrar quem está na porta resolve o caso
 * comum (servidor largado de outra sessão); trocar a porta resolve o conflito
 * de verdade; subir mesmo assim existe porque às vezes o painel não sabe de
 * algo que a pessoa sabe — e aí a decisão passa a ser dela, registrada.
 */
async function resolverPortaOcupada(project) {
  let checagem;
  try {
    checagem = await api.preflight(project.id);
  } catch {
    return 'cancelar';
  }

  const linhas = checagem.blockers.map((b) => {
    const dono = b.occupant_project_name ? `, do ${b.occupant_project_name}` : '';
    return `• ${b.port} (${b.service_label}): ${b.occupant}${dono}`;
  });

  const paravel = checagem.blockers.find((b) => b.resolvable);

  const texto =
    `${project.name} não subiu porque a porta já está ocupada:\n\n` +
    `${linhas.join('\n')}\n\n` +
    (paravel
      ? `OK encerra o processo ${paravel.stoppable_pid} e sobe.\n`
      : 'O painel não pode encerrar quem está na porta.\n') +
    'Cancelar deixa como está — use a tela Ports para trocar a porta.';

  if (!window.confirm(texto)) {
    toast(`${project.name}: subida cancelada.`, {
      kind: 'warning',
      meta: 'A tela Ports mostra quem está em cada porta.',
    });
    return 'cancelar';
  }

  if (!paravel) return 'forcar';

  try {
    await api.stopProcess(paravel.stoppable_pid);
    toast(`Processo ${paravel.stoppable_pid} encerrado.`, { kind: 'success' });
    return 'repetir';
  } catch (error) {
    showError(error);
    return 'cancelar';
  }
}

async function subirAmbiente(project, { force = false } = {}) {
  let aceito;
  try {
    aceito = await api.environmentUp(project.id, force);
  } catch (error) {
    // O pré-voo recusou antes de tentar: é informação, não falha. Descobrir
    // pelo erro do Compose, no meio da subida, custava a espera inteira para
    // chegar a algo que já se sabia.
    if (error.code !== 'PORTS_BUSY') throw error;

    const decisao = await resolverPortaOcupada(project);
    if (decisao === 'cancelar') return 'off';
    return subirAmbiente(project, { force: decisao === 'forcar' });
  }

  const job = await waitJob(aceito.job_id);

  if (job.status !== 'SUCCESS') {
    toast(`${project.name}: a subida terminou em ${job.status.toLowerCase()}.`, {
      kind: 'error',
      meta: job.message ?? 'A aba Docker do projeto mostra a saída completa.',
    });
    return 'off';
  }

  // Quem decide o estado exibido é a verificação, nunca o código de saída. O
  // botão que se declarava ligado por conta própria era desmentido pelo
  // verificador trinta segundos depois, e voltava sozinho — parecendo que a
  // ordem não tinha sido obedecida.
  const respondeu = await esperarResposta(project.id);
  if (respondeu) {
    toast(`${project.name}: no ar.`, { kind: 'success' });
    return 'on';
  }

  toast(`${project.name}: subiu, mas nenhuma porta declarada respondeu ainda.`, {
    kind: 'warning',
    meta: 'Pode estar compilando. O console do job mostra o progresso.',
  });
  return 'off';
}

/** Para a aplicação. Os containers ficam de pé, salvo pedido explícito.
 *
 * A assimetria vem do uso real: banco e fila são caros de subir e não mudam
 * entre uma execução e outra da aplicação. Derrubá-los a cada parada do
 * backend trocaria um ciclo de dois segundos por um de trinta. Quem quiser o
 * desligamento completo segura Shift ao clicar — fora do caminho do clique
 * diário, mas alcançável sem menu.
 */
async function pararAplicacao(project, { derrubarDocker = false } = {}) {
  const { stopped, job_id: jobId } = await api.environmentDown(project.id, derrubarDocker);

  if (stopped === 'nothing') {
    // Nem aplicação de pé nem Compose. Dizer isso é o único jeito de distinguir
    // "não havia nada ligado" de "o botão não funcionou" — e essa distinção era
    // justamente a que faltava.
    toast(`${project.name}: não havia nada no ar para desligar.`, { kind: 'warning' });
    return 'off';
  }

  // `compose down` demora, e a resposta veio antes de ele terminar. Anunciar
  // sucesso aqui era o que fazia o painel dizer "ambiente derrubado" com os
  // containers ainda de pé.
  if (jobId) {
    const job = await waitJob(jobId);
    if (job?.status !== 'SUCCESS') {
      toast(`${project.name}: não foi possível derrubar os containers.`, {
        kind: 'error',
        meta: job?.message ?? 'A aba Docker do projeto mostra a saída completa.',
      });
      return 'on';
    }
  }

  const real = await api.checkServices(project.id).catch(() => ({ items: [] }));
  const aindaResponde = real.items.some((item) => item.state === 'ONLINE');

  if (stopped === 'external') {
    // Vale dizer que o alvo não era do painel: quem subiu no terminal precisa
    // saber que aquele processo morreu, senão vai procurá-lo depois.
    toast(`${project.name}: parei o servidor que estava rodando fora do painel.`, {
      kind: 'success',
      meta: 'Ele não tinha sido iniciado daqui, mas roda dentro do projeto.',
    });
  } else if (stopped === 'docker') {
    toast(`${project.name}: containers parados.`, { kind: 'success' });
  } else if (aindaResponde) {
    // O caso normal deste fluxo, e por isso a mensagem é informativa e não de
    // erro: a aplicação parou e o ambiente continua atendendo, que é
    // exatamente o que se pediu.
    toast(`${project.name}: aplicação parada. Os containers seguem no ar.`, {
      kind: 'success',
      meta: 'Shift+clique para derrubar os containers também.',
    });
  } else {
    toast(`${project.name}: parado.`, { kind: 'success' });
  }

  // O estado do botão é o da **aplicação**, não o do ambiente: o chip do
  // Docker ao lado é quem responde pelos containers.
  return 'off';
}

const MOTIVOS = {
  missing: 'O diretório deste projeto não existe mais.',
  semComando:
    'O DevCockpit não achou como subir este projeto: sem Compose, sem script ' +
    'de dev no package.json e sem framework Python reconhecido. Declare o ' +
    'bloco `run:` no devcockpit.yml do projeto.',
};

const TEXTO = {
  on: { label: 'Ligado', acao: 'Desligar' },
  off: { label: 'Desligado', acao: 'Ligar' },
  busy: { label: 'Aguarde…', acao: 'aguardar' },
};

//: A dica diz o que o clique faz *neste* projeto. "Clique para subir o
//: Compose" num projeto de `npm run dev` estaria simplesmente errado.
const DICA = {
  docker: {
    on: 'Clique para parar a aplicação. Os containers ficam de pé.',
    off: 'Clique para subir os containers e, em seguida, a aplicação.',
  },
  server: {
    on: 'Clique para parar o servidor de desenvolvimento.',
    off: 'Clique para subir o servidor de desenvolvimento do projeto.',
  },
};

/**
 * Chave liga/desliga de um projeto.
 *
 * @param {object} project    projeto (summary ou detail)
 * @param {object} options
 * @param {boolean} options.on         estado observado agora
 * @param {boolean} options.compact    só o ícone, para o trilho lateral
 * @param {Function} options.onChanged chamado depois que a operação termina
 */
/** A aplicação deste projeto está no ar?
 *
 * Uma pergunta, uma resposta — e é a resposta que o **botão** dá, então ela
 * precisa valer para as duas telas que o mostram. Estavam divergindo:
 *
 * - a página de Projects olhava só `app_running`, o **processo nativo**, e
 *   dizia "Desligado" para uma aplicação servida por container;
 * - a barra lateral olhava "algum serviço responde", e diria "Ligado" com só o
 *   Postgres atendendo e o backend parado — a confusão do caso ZAPBOT, que o
 *   chip do Docker existe para evitar.
 *
 * A ordem é de evidência: o que foi **medido** sobre a aplicação primeiro
 * (`app_online`), o processo nativo depois, e "algum serviço" só como último
 * recurso — para quem chamar isto sem os campos da listagem.
 *
 * O botão para aplicação em container também (`environmentDown` devolve
 * `stopped: 'docker'`), então dizer "Desligado" ali não era só impreciso: era
 * esconder o desligar de quem queria desligar.
 */
export function aplicacaoNoAr(project, { online = 0 } = {}) {
  if (project.app_online === true) return true;
  if (project.app_running === true) return true;
  if (project.app_online === false || project.app_running === false) return false;
  return online > 0;
}


export function powerToggle(project, { on = false, compact = false, onChanged } = {}) {
  const missing = project.status === 'MISSING';
  const docker = hasDocker(project);
  // O botão sobe o ambiente inteiro, na ordem: containers primeiro, aplicação
  // depois. Quem decide a ordem é o servidor — a tela não tem como saber, sem
  // uma chamada por card, se o projeto declara `run:`.
  // `can_start` vem do servidor, que leu o disco; a heurística de stack é a
  // reserva para quem chamar isto com um projeto que não passou pela lista.
  const sabeSubir = project.can_start ?? (docker || hasRunnableStack(project));
  const habilitado = sabeSubir && !missing;
  const motivo = missing ? MOTIVOS.missing : MOTIVOS.semComando;
  const via = docker ? 'docker' : 'server';

  let estado = on ? 'on' : 'off';
  //: Rótulo do estado `busy`: "Subindo…" e "Parando…" dizem o que está
  //: acontecendo; um "aguarde" genérico faria o usuário adivinhar.
  let gerundio = '';

  const rotulo = el('span', { class: 'power__label', text: TEXTO[estado].label });
  const botao = el(
    'button',
    {
      class: `power${compact ? ' power--compact' : ''}`,
      type: 'button',
      disabled: !habilitado,
      dataset: { state: estado },
      'aria-pressed': estado === 'on' ? 'true' : 'false',
    },
    [el('span', { class: 'power__knob' }, [icon('power', { size: 13 })]), rotulo]
  );

  const desenhar = () => {
    botao.dataset.state = estado;
    rotulo.textContent = estado === 'busy' ? gerundio : TEXTO[estado].label;
    botao.setAttribute('aria-pressed', estado === 'on' ? 'true' : 'false');
    botao.disabled = !habilitado || estado === 'busy';
    botao.setAttribute(
      'aria-label',
      habilitado ? `${TEXTO[estado].acao} ${project.name}` : `${project.name}: ${motivo}`
    );
    botao.title = habilitado
      ? (DICA[via]?.[estado === 'busy' ? 'on' : estado] ?? '')
      : motivo;
  };

  botao.addEventListener('click', async (event) => {
    if (!habilitado || estado === 'busy') return;

    const ligando = estado !== 'on';
    const anterior = estado;
    estado = 'busy';
    gerundio = ligando ? 'Subindo…' : 'Parando…';
    desenhar();

    try {
      estado = ligando
        ? await subirAmbiente(project)
        : await pararAplicacao(project, { derrubarDocker: event.shiftKey });
    } catch (error) {
      estado = anterior;
      showError(error);
    }

    desenhar();
    onChanged?.(estado === 'on');
  });

  desenhar();
  return botao;
}

/** Chip do ambiente: quantos containers do projeto estão de pé.
 *
 * Existe porque o botão grande passou a falar só da **aplicação**. Sem este
 * chip, parar a aplicação deixaria o painel dizendo "Desligado" com o Postgres
 * atendendo na porta — exatamente a confusão que o caso do ZAPBOT expôs, onde
 * o estado exibido não correspondia ao que a máquina fazia.
 *
 * O clique aqui é o desligamento completo, fora do caminho do clique diário.
 *
 * @param {object} project
 * @param {object} options
 * @param {number|null} options.running  containers no ar; `null` = não sabido
 * @param {Function} options.onChanged
 */
export function dockerChip(project, { running = null, onChanged } = {}) {
  if (!hasDocker(project)) return null;

  const noAr = typeof running === 'number' && running > 0;
  // Sem número. O que chega aqui é a contagem de **serviços que respondem**, e
  // o chip fala de **containers** — dois fatos diferentes que coincidem por
  // acaso quando todo serviço do projeto vive em container. Num projeto com
  // aplicação nativa e um container, ele dizia "2 no ar" para um container só.
  //
  // Contar container de verdade custaria um `docker ps` por card, que é o que
  // a NFR-010 proíbe na lista. Entre um número preciso e errado e uma
  // afirmação verdadeira sem número, a segunda. O card já mostra "5/6 online"
  // logo acima, então nada se perde.
  const texto = running === null ? 'containers' : noAr ? 'ambiente no ar' : 'containers parados';

  const chip = el(
    'button',
    {
      class: 'docker-chip',
      type: 'button',
      dataset: { on: noAr ? 'true' : 'false' },
      disabled: !noAr,
      title: noAr
        ? 'Derrubar os containers deste projeto.'
        : 'Nada deste projeto respondeu na última verificação.',
      'aria-label': noAr
        ? `Derrubar os containers de ${project.name}`
        : `${project.name}: containers parados`,
    },
    [icon('container', { size: 12 }), el('span', { text: texto })]
  );

  chip.addEventListener('click', async () => {
    if (!noAr) return;
    // Derrubar o ambiente é o que a pessoa faz no fim do expediente, e o
    // caminho de volta custa minutos. Vale a confirmação.
    const segue = window.confirm(
      `Derrubar os containers de "${project.name}"?\n\n` +
        'A aplicação para junto. Subir de novo leva o tempo do `compose up`.'
    );
    if (!segue) return;

    chip.disabled = true;
    const original = chip.querySelector('span').textContent;
    chip.querySelector('span').textContent = 'derrubando…';
    try {
      const { job_id: jobId } = await api.environmentDown(project.id, true);
      // Esperar o job antes de anunciar. Sem isto o chip dizia "ambiente
      // derrubado" no instante da resposta, enquanto o `compose down` mal tinha
      // começado — e o container voltava a aparecer no ciclo seguinte.
      const job = jobId ? await waitJob(jobId) : null;

      if (jobId && job?.status !== 'SUCCESS') {
        chip.disabled = false;
        chip.querySelector('span').textContent = original;
        toast(`${project.name}: os containers não foram derrubados.`, {
          kind: 'error',
          meta: job?.message ?? 'A aba Docker do projeto mostra a saída completa.',
        });
        return;
      }

      toast(`${project.name}: ambiente derrubado.`, { kind: 'success' });
      onChanged?.(false);
    } catch (error) {
      chip.disabled = false;
      chip.querySelector('span').textContent = original;
      showError(error);
    }
  });

  return chip;
}
