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
async function subirAmbiente(project) {
  const aceito = await api.environmentUp(project.id);
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
  const texto =
    running === null ? 'containers' : noAr ? `${running} no ar` : 'containers parados';

  const chip = el(
    'button',
    {
      class: 'docker-chip',
      type: 'button',
      dataset: { on: noAr ? 'true' : 'false' },
      disabled: !noAr,
      title: noAr
        ? 'Derrubar os containers deste projeto.'
        : 'Nenhum container deste projeto está no ar.',
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
