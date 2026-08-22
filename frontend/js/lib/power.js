// Liga/desliga de projeto, num controle só.
//
// Antes só existia dentro da aba Docker, em quatro botões soltos ("Subir",
// "Parar", "Reiniciar", "Derrubar") que não diziam em que estado o projeto
// está — o botão "Subir" tinha a mesma cara com tudo no ar e com tudo parado.
// Aqui o controle **mostra o estado** e a ação é a consequência dele.
//
// Dois caminhos para ligar, escolhidos pelo que o projeto é:
//
// - com Compose, `docker compose up`/`stop`, que roda como job;
// - sem Compose, o servidor de desenvolvimento do próprio projeto
//   (`npm run dev`, `uvicorn`, `flask run`), que roda como processo de vida
//   longa. Este segundo caminho existe porque a maioria dos projetos não tem
//   Compose, e para eles o painel sabia dizer que estava parado sem saber
//   fazer nada a respeito — sobrava abrir o terminal e digitar o comando.
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

/** Reverifica os serviços do projeto e devolve o estado que a máquina mostra.
 *
 * `stop` do Compose devolve sucesso assim que os containers param, mas parar
 * container não é o mesmo que a porta ficar livre. Perguntar aqui é uma
 * requisição a mais num clique que o usuário acabou de dar — barato, e evita
 * que a tela afirme algo que o próximo ciclo do verificador vai desmentir.
 */
async function confirmarEstado(projectId, acao) {
  try {
    const { items } = await api.checkServices(projectId);
    return { ligado: items.some((item) => item.state === 'ONLINE'), items };
  } catch {
    // Verificação falhou: fica com o resultado otimista da ação, que é melhor
    // que travar o botão. O poller corrige na próxima volta.
    return { ligado: acao === 'up', items: [] };
  }
}

/** Liga ou desliga o servidor de desenvolvimento do projeto.
 *
 * Sem job: o processo nasce e a requisição acaba. O que demora é o servidor
 * ficar pronto para atender, e quem responde isso é a verificação de porta —
 * por isso o estado exibido sai dela, não do fato de o processo ter nascido.
 */
async function acionarServidor(project, { ligando, anterior, aplicar }) {
  try {
    const estadoServidor = ligando
      ? await api.startServer(project.id)
      : await api.stopServer(project.id);

    if (!ligando) {
      aplicar('off');
      toast(`${project.name}: servidor parado.`, { kind: 'success' });
      return;
    }

    // Um servidor de desenvolvimento leva alguns segundos entre nascer e
    // atender. Perguntar imediatamente devolveria "desligado" para algo que
    // acabou de subir, e o botão voltaria sozinho — o mesmo mal-entendido que
    // o caminho do Docker já tinha.
    const respondeu = await esperarResposta(project.id);
    aplicar(respondeu ? 'on' : 'off');

    if (respondeu) {
      toast(`${project.name}: no ar.`, { kind: 'success' });
    } else {
      toast(`${project.name}: processo iniciado, mas a porta ainda não responde.`, {
        kind: 'warning',
        meta: `pid ${estadoServidor.pid} · veja o log na aba do projeto.`,
      });
    }
  } catch (error) {
    aplicar(anterior);
    showError(error);
  }
}

//: Quanto tempo esperar o servidor recém-subido começar a atender, e de quanto
//: em quanto perguntar. Oito segundos cobre Vite e uvicorn com folga; o que
//: passar disso o verificador de background resolve sozinho.
const ESPERA_MAX_MS = 8000;
const ESPERA_PASSO_MS = 800;

async function esperarResposta(projectId) {
  const limite = Date.now() + ESPERA_MAX_MS;
  for (;;) {
    const { items } = await api.checkServices(projectId).catch(() => ({ items: [] }));
    if (items.some((item) => item.state === 'ONLINE')) return true;
    if (Date.now() >= limite) return false;
    await new Promise((resolve) => window.setTimeout(resolve, ESPERA_PASSO_MS));
  }
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
  docker: { on: 'Clique para parar os containers.', off: 'Clique para subir o Compose.' },
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
  // Compose primeiro: num projeto que tem os dois, subir a stack inteira é o
  // que a pessoa quer — o servidor solto deixaria o banco de fora.
  const via = docker ? 'docker' : hasRunnableStack(project) ? 'server' : null;
  const habilitado = via !== null && !missing;
  const motivo = missing ? MOTIVOS.missing : MOTIVOS.semComando;

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

  botao.addEventListener('click', async () => {
    if (!habilitado || estado === 'busy') return;

    const ligando = estado !== 'on';
    const anterior = estado;
    estado = 'busy';
    gerundio = ligando ? 'Subindo…' : 'Parando…';
    desenhar();

    if (via === 'server') {
      await acionarServidor(project, { ligando, anterior, aplicar: (novo) => (estado = novo) });
      desenhar();
      onChanged?.(estado === 'on');
      return;
    }

    const acao = ligando ? 'up' : 'stop';

    try {
      const aceito = await api.dockerAction(project.id, acao);
      const job = await waitJob(aceito.job_id);

      if (job.status === 'SUCCESS') {
        // O comando terminou, mas quem decide o estado exibido é a verificação
        // — não o código de saída. Antes o botão se declarava desligado por
        // conta própria e o verificador, 30 s depois, dizia o contrário: o
        // botão voltava sozinho para "Ligado" e parecia que a ordem não tinha
        // sido obedecida. Acontece de verdade quando a porta declarada é
        // servida por algo de fora do Compose (um Postgres nativo na mesma
        // porta do container, por exemplo).
        const real = await confirmarEstado(project.id, acao);
        estado = real.ligado ? 'on' : 'off';

        if (acao === 'stop' && real.ligado) {
          toast(`${project.name}: containers parados, mas a porta continua respondendo.`, {
            kind: 'warning',
            meta: 'Algo fora do Compose está ocupando a porta. Veja em Ports quem é.',
          });
        } else {
          toast(`${project.name}: ${acao === 'up' ? 'no ar' : 'parado'}.`, { kind: 'success' });
        }
      } else {
        estado = anterior;
        toast(`${project.name}: "${acao}" terminou em ${job.status.toLowerCase()}.`, {
          kind: 'error',
          meta: 'A aba Docker do projeto mostra a saída completa.',
        });
      }
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
