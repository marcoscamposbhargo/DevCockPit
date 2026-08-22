// Liga/desliga de projeto, num controle só.
//
// Antes só existia dentro da aba Docker, em quatro botões soltos ("Subir",
// "Parar", "Reiniciar", "Derrubar") que não diziam em que estado o projeto
// está — o botão "Subir" tinha a mesma cara com tudo no ar e com tudo parado.
// Aqui o controle **mostra o estado** e a ação é a consequência dele.
//
// Só liga o que o DevCockpit sabe ligar: hoje, Compose. Projeto sem Compose
// aparece desabilitado **com o motivo**, nunca como um clique que falha depois
// (mesma regra de lib/actions.js).

import { api } from './api.js';
import { el } from './dom.js';
import { icon } from './icons.js';
import { showError, toast } from './ui.js';

const DOCKER_TECHS = new Set(['docker', 'docker-compose']);

const ESTADOS_FINAIS = new Set(['SUCCESS', 'FAILED', 'TIMEOUT', 'CANCELLED']);
const POLL_MS = 900;

/** Heurística barata: a stack detectada já diz se há Compose ou Dockerfile.
 *
 * Perguntar ao Docker por projeto custaria uma chamada por card — a lista de
 * projetos não pode disparar isso (NFR-010). */
export function hasDocker(project) {
  const techs = project.technologies ?? [];
  return techs.some((tech) => DOCKER_TECHS.has(typeof tech === 'string' ? tech : tech.name));
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

const MOTIVOS = {
  missing: 'O diretório deste projeto não existe mais.',
  semCompose:
    'Sem Compose detectado: o DevCockpit não tem como subir este projeto. ' +
    'Abra o terminal e use o comando do próprio projeto.',
};

const TEXTO = {
  on: { label: 'Ligado', acao: 'Desligar', dica: 'Clique para parar os containers.' },
  off: { label: 'Desligado', acao: 'Ligar', dica: 'Clique para subir o Compose.' },
  busy: { label: 'Aguarde…', acao: 'aguardar', dica: 'Operação em andamento.' },
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
  const habilitado = docker && !missing;
  const motivo = missing ? MOTIVOS.missing : MOTIVOS.semCompose;

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
    botao.title = habilitado ? TEXTO[estado].dica : motivo;
  };

  botao.addEventListener('click', async () => {
    if (!habilitado || estado === 'busy') return;

    const acao = estado === 'on' ? 'stop' : 'up';
    const anterior = estado;
    estado = 'busy';
    gerundio = acao === 'up' ? 'Subindo…' : 'Parando…';
    desenhar();

    try {
      const aceito = await api.dockerAction(project.id, acao);
      const job = await waitJob(aceito.job_id);

      if (job.status === 'SUCCESS') {
        estado = acao === 'up' ? 'on' : 'off';
        toast(`${project.name}: ${acao === 'up' ? 'no ar' : 'parado'}.`, { kind: 'success' });
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
