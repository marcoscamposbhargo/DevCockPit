// Console de job: saída ao vivo, autoscroll pausável, cancelamento (US-042).
//
// Painel, nunca modal: o usuário precisa acompanhar o progresso enquanto olha
// o resto da tela. Modal esconde justamente o que se quer ver.
//
// SSE com fallback para polling. Antivírus e proxy locais no Windows fecham
// conexão persistente sem aviso, e uma dependência única aí seria frágil.

import { api } from './api.js';
import { el } from './dom.js';
import { duration } from './format.js';

const POLL_INTERVAL_MS = 700;
const FINAL_STATES = new Set(['SUCCESS', 'FAILED', 'TIMEOUT', 'CANCELLED']);

const STATUS_STYLE = {
  PENDING: 'var(--fg-muted)',
  RUNNING: 'var(--status-starting)',
  SUCCESS: 'var(--status-running)',
  FAILED: 'var(--status-error)',
  TIMEOUT: 'var(--status-warning)',
  CANCELLED: 'var(--fg-muted)',
};

export function jobConsole({ jobId, title, onFinish }) {
  let autoscroll = true;
  let delivered = 0;
  let source = null;
  let pollTimer = 0;
  let finished = false;

  const output = el('pre', { class: 'job-console__output', tabindex: '0' });
  const statusEl = el('span', { class: 'job-console__status', text: 'iniciando…' });
  const timeEl = el('span', { class: 'job-console__time', text: '' });
  const transportEl = el('span', { class: 'job-console__transport', text: '' });

  const cancelBtn = el('button', {
    class: 'btn btn--sm btn--danger',
    text: 'Cancelar',
    onClick: async () => {
      cancelBtn.disabled = true;
      cancelBtn.textContent = 'Cancelando…';
      try {
        await api.cancelJob(jobId);
      } catch {
        cancelBtn.disabled = false;
        cancelBtn.textContent = 'Cancelar';
      }
    },
  });

  const autoscrollBtn = el('button', {
    class: 'btn btn--sm',
    text: 'Autoscroll: on',
    onClick: () => {
      autoscroll = !autoscroll;
      autoscrollBtn.textContent = `Autoscroll: ${autoscroll ? 'on' : 'off'}`;
      if (autoscroll) output.scrollTop = output.scrollHeight;
    },
  });

  // Rolar para cima manualmente pausa o autoscroll: é o que a pessoa quis dizer.
  output.addEventListener('scroll', () => {
    const noFim = output.scrollHeight - output.scrollTop - output.clientHeight < 24;
    if (!noFim && autoscroll) {
      autoscroll = false;
      autoscrollBtn.textContent = 'Autoscroll: off';
    }
  });

  const root = el('section', { class: 'job-console' }, [
    el('header', { class: 'job-console__header' }, [
      el('strong', { text: title }),
      statusEl,
      timeEl,
      transportEl,
      el('span', { style: 'margin-left:auto; display:flex; gap:var(--sp-2)' }, [
        autoscrollBtn,
        cancelBtn,
      ]),
    ]),
    output,
  ]);

  function appendLines(lines) {
    if (!lines.length) return;
    for (const line of lines) {
      output.append(document.createTextNode(`${line}\n`));
    }
    if (autoscroll) output.scrollTop = output.scrollHeight;
  }

  function setStatus(status, extra = {}) {
    statusEl.textContent = status.toLowerCase();
    statusEl.style.color = STATUS_STYLE[status] ?? 'inherit';
    if (extra.duration_ms !== undefined && extra.duration_ms !== null) {
      timeEl.textContent = duration(extra.duration_ms);
    }
    if (extra.message) {
      appendLines([`— ${extra.message}`]);
    }
  }

  function finish(status, extra) {
    if (finished) return;
    finished = true;
    cancelBtn.disabled = true;
    cancelBtn.textContent = 'Encerrado';
    setStatus(status, extra ?? {});
    stop();
    // Anuncia para leitor de tela: a conclusão é a informação que importa.
    root.setAttribute('aria-live', 'polite');
    onFinish?.(status, extra);
  }

  function stop() {
    if (source) {
      source.close();
      source = null;
    }
    if (pollTimer) {
      window.clearInterval(pollTimer);
      pollTimer = 0;
    }
  }

  async function pollOnce() {
    try {
      const job = await api.getJob(jobId, delivered);
      if (job.output) {
        appendLines(job.output.split('\n'));
        delivered = job.line_count;
      }
      if (FINAL_STATES.has(job.status)) {
        finish(job.status, job);
      } else {
        setStatus(job.status, job);
      }
    } catch (error) {
      finish('FAILED', { message: error.message });
    }
  }

  function startPolling(reason) {
    if (pollTimer || finished) return;
    transportEl.textContent = `polling (${reason})`;
    pollOnce();
    pollTimer = window.setInterval(pollOnce, POLL_INTERVAL_MS);
  }

  function startStream() {
    if (typeof window.EventSource !== 'function') {
      startPolling('sem EventSource');
      return;
    }

    transportEl.textContent = 'stream';
    source = new EventSource(`/api/jobs/${encodeURIComponent(jobId)}/stream`);

    source.addEventListener('log', (event) => {
      const data = JSON.parse(event.data);
      appendLines(data.lines);
      delivered = data.revision;
      setStatus('RUNNING');
    });

    source.addEventListener('end', (event) => {
      finish(JSON.parse(event.data).status, JSON.parse(event.data));
    });

    source.onerror = () => {
      // Não distinguimos queda de conexão de fim de stream: o polling
      // resolve os dois e é idempotente graças ao `after`.
      if (!finished) {
        stop();
        startPolling('stream caiu');
      }
    };
  }

  startStream();

  return { element: root, stop };
}
