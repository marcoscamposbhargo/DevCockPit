// Único ponto de acesso à API.
//
// Centraliza o cabeçalho de cliente exigido pela defesa D5 e traduz o envelope
// de erro do backend em uma exceção com código estável.

const BASE = '/api';

export class ApiError extends Error {
  constructor({ code, message, correlationId, status }) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.correlationId = correlationId;
    this.status = status;
  }
}

async function request(method, path, { body, params, proposta } = {}) {
  const url = new URL(BASE + path, window.location.origin);
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.set(key, String(value));
    }
  }

  const headers = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (method !== 'GET') headers['X-DevCockpit-Client'] = 'web';
  if (proposta) headers['X-DevCockpit-Proposal'] = proposta;

  let response;
  try {
    response = await fetch(url, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (cause) {
    throw new ApiError({
      code: 'NETWORK_ERROR',
      message: 'Não foi possível falar com o servidor do DevCockpit.',
      status: 0,
    });
  }

  if (response.status === 204) return null;

  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    const error = payload?.error ?? {};
    throw new ApiError({
      code: error.code ?? 'INTERNAL_ERROR',
      message: error.message ?? `Falha na requisição (${response.status}).`,
      correlationId: error.correlation_id,
      status: response.status,
    });
  }

  return payload;
}

/** Pergunta com resposta em stream (SSE), compartilhada pelas duas rotas de IA.
 *
 * `fetch` e não `EventSource`: a pergunta vai num POST, e `EventSource` só
 * sabe fazer GET. O parser é curto porque o formato é curto.
 *
 * `model` é `'default'` ou `'alt'` — a escolha entre os dois modelos que o
 * servidor configurou, nunca o nome de um modelo.
 */
async function sseAsk(path, body, { onChunk, onError, model = 'default' } = {}) {
  const resposta = await fetch(new URL(BASE + path, window.location.origin), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-DevCockpit-Client': 'web' },
    body: JSON.stringify({ ...body, model }),
  });

  if (!resposta.ok) {
    const payload = await resposta.json().catch(() => null);
    const erro = payload?.error ?? {};
    throw new ApiError({
      code: erro.code ?? 'INTERNAL_ERROR',
      message: erro.message ?? `Falha na requisição (${resposta.status}).`,
      status: resposta.status,
    });
  }

  const leitor = resposta.body.getReader();
  const decodificador = new TextDecoder();
  let resto = '';

  for (;;) {
    const { value, done } = await leitor.read();
    if (done) break;
    resto += decodificador.decode(value, { stream: true });

    const blocos = resto.split('\n\n');
    resto = blocos.pop() ?? '';

    for (const bloco of blocos) {
      const linhas = bloco.split('\n');
      const evento = linhas.find((l) => l.startsWith('event:'))?.slice(6).trim();
      const dados = linhas.find((l) => l.startsWith('data:'))?.slice(5).trim();
      if (!dados) continue;

      const payload = JSON.parse(dados);
      if (evento === 'chunk') onChunk?.(payload.text ?? '');
      else if (evento === 'error') onError?.(payload);
    }
  }
}

export const api = {
  health: () => request('GET', '/health'),

  listProjects: (params) => request('GET', '/projects', { params }),
  getProject: (id) => request('GET', `/projects/${encodeURIComponent(id)}`),
  createProject: (body) => request('POST', '/projects', { body }),
  updateProject: (id, body) => request('PATCH', `/projects/${encodeURIComponent(id)}`, { body }),
  deleteProject: (id) => request('DELETE', `/projects/${encodeURIComponent(id)}`),

  detectProject: (id) => request('POST', `/projects/${encodeURIComponent(id)}/detect`),

  gitStatus: (id) => request('GET', `/projects/${encodeURIComponent(id)}/git/status`),
  gitCommits: (id, limit = 20) =>
    request('GET', `/projects/${encodeURIComponent(id)}/git/commits`, { params: { limit } }),
  gitBranches: (id) => request('GET', `/projects/${encodeURIComponent(id)}/git/branches`),
  gitRemotes: (id) => request('GET', `/projects/${encodeURIComponent(id)}/git/remotes`),

  manifestStatus: (id) => request('GET', `/projects/${encodeURIComponent(id)}/manifest`),
  manifestPreview: (id) =>
    request('GET', `/projects/${encodeURIComponent(id)}/manifest/preview`),
  importManifest: (id) =>
    request('POST', `/projects/${encodeURIComponent(id)}/manifest/import`),
  exportManifest: (id) =>
    request('POST', `/projects/${encodeURIComponent(id)}/manifest/export`, {
      body: { confirm: true },
    }),

  dashboard: () => request('GET', '/dashboard'),

  // Cockpit AI — Fase 1. Nada aqui fala com modelo: é sessão, memória e o
  // briefing do dia, montados do que o painel já mede.
  day: () => request('GET', '/ai/day'),
  sessions: (id) => request('GET', `/projects/${encodeURIComponent(id)}/sessions`),
  startSession: (id, objective) =>
    request('POST', `/projects/${encodeURIComponent(id)}/sessions/start`, {
      body: { objective: objective || null },
    }),
  endSession: (id, summary, nextSteps) =>
    request('POST', `/projects/${encodeURIComponent(id)}/sessions/end`, {
      body: { summary: summary || null, next_steps: nextSteps || null },
    }),
  projectMemory: (id, kind) =>
    request('GET', `/projects/${encodeURIComponent(id)}/memory`, { params: { kind } }),
  createProjectMemory: (id, body) =>
    request('POST', `/projects/${encodeURIComponent(id)}/memory`, { body }),
  tasks: (id, includeDone = true) =>
    request('GET', `/projects/${encodeURIComponent(id)}/tasks`, {
      params: { include_done: includeDone },
    }),
  createTask: (id, body) => request('POST', `/projects/${encodeURIComponent(id)}/tasks`, { body }),
  updateTask: (taskId, body) => request('PATCH', `/ai/tasks/${taskId}`, { body }),
  deleteTask: (taskId) => request('DELETE', `/ai/tasks/${taskId}`),

  aiStatus: () => request('GET', '/ai/status'),
  /** Os chapéus e os botões de cada um, já resolvidos para este projeto. */
  especialistas: (projectId) =>
    request('GET', '/ai/specialists', { params: { project_id: projectId } }),
  chatHistory: (id) => request('GET', `/projects/${encodeURIComponent(id)}/chat`),

  /** Pergunta com resposta em stream (SSE).
   *
   * `fetch` e não `EventSource`: a pergunta vai num POST, e `EventSource` só
   * sabe fazer GET. O parser é curto porque o formato é curto.
   */
  /** Pergunta avulsa, sem projeto: o assistente de terminal.
   *
   * Mesmo transporte do chat, rota diferente — e a diferença que importa está
   * no servidor: aqui nenhum contexto de projeto é montado.
   */
  askQuick: (question, opcoes = {}) => sseAsk('/ai/ask', { question }, opcoes),

  /** O que a IA faria com esta frase — sem fazer.
   *
   * Devolve `{ proposal, message }`. `proposal` vem `null` na maioria das
   * frases, porque a maior parte do que se digita é dúvida e não ordem.
   */
  proposeAction: (question, model = 'default') =>
    request('POST', '/ai/propose', { body: { question, model } }),

  /** Executa a ação **proposta**, pela rota que a proposta indicou.
   *
   * O caminho não é inventado pelo cliente: ele veio de `proposeAction`, do
   * registro fechado do servidor, e é a mesma rota que o botão equivalente
   * chama. A IA não ganha caminho de execução próprio (defesa D-A3).
   */
  runProposal: (proposal) => {
    const caminho = proposal.path.replace(/^\/api/, '');
    // O bilhete que o servidor emitiu ao propor volta aqui. Não é o cliente
    // afirmando "isto foi a IA" — é o servidor reconhecendo a própria proposta
    // e, com isso, gravando a autoria na auditoria (Fase 3.6).
    return request(proposal.method, caminho, { proposta: proposal.id });
  },

  chatStream: (id, question, opcoes = {}) =>
    sseAsk(
      `/projects/${encodeURIComponent(id)}/chat`,
      // `agent` fixa o especialista; sem ele, a regra do servidor escolhe.
      { question, agent: opcoes.agente ?? null },
      opcoes
    ),

  globalMemory: (kind) => request('GET', '/ai/memory', { params: { kind } }),
  createGlobalMemory: (body) => request('POST', '/ai/memory', { body }),
  confirmMemory: (memoryId) => request('POST', `/ai/memory/${memoryId}/confirm`),
  deleteMemory: (memoryId) => request('DELETE', `/ai/memory/${memoryId}`),
  analytics: (days = 14) => request('GET', '/analytics', { params: { days } }),

  listServices: (id) => request('GET', `/projects/${encodeURIComponent(id)}/services`),
  checkServices: (id) => request('POST', `/projects/${encodeURIComponent(id)}/services/check`),
  // Substituição em bloco: o backend não tem PATCH de serviço solto, então
  // editar uma porta é reenviar a lista inteira do projeto.
  replaceServices: (id, items) =>
    request('PUT', `/projects/${encodeURIComponent(id)}/services`, { body: { items } }),
  ports: () => request('GET', '/services/ports'),

  openVsCode: (id) => request('POST', `/projects/${encodeURIComponent(id)}/open/vscode`),
  // Sem projeto: abre o editor vazio, que restaura a última sessão dele.
  // Nenhum caminho é enviado — não há o que o cliente pudesse forjar.
  openEditor: () => request('POST', '/services/open/vscode'),
  openFolder: (id) => request('POST', `/projects/${encodeURIComponent(id)}/open/folder`),
  openTerminal: (id) => request('POST', `/projects/${encodeURIComponent(id)}/open/terminal`),
  // A chave é obrigatória e a falha por ausência dela era ilegível: o backend
  // respondia "service_key: Field required" e a tela mostrava isso cru, sem
  // dizer qual botão nem o que fazer. Falhar aqui, com o nome do chamador,
  // custa uma linha e economiza a caçada.
  openBrowser: (id, serviceKey) => {
    if (!serviceKey) {
      throw new ApiError({
        code: 'MISSING_SERVICE_KEY',
        message: 'Não foi possível identificar qual serviço abrir.',
        status: 0,
      });
    }
    return request('POST', `/projects/${encodeURIComponent(id)}/open/browser`, {
      body: { service_key: serviceKey },
    });
  },

  // Servidor de desenvolvimento do projeto (sem Docker). Nenhuma destas rotas
  // aceita comando: o cliente manda o id, e o comando sai do devcockpit.yml ou
  // da detecção, no servidor.
  // Todos os servidores no ar, de uma vez. Sem isto, saber o que está rodando
  // exige abrir projeto por projeto — e no fim do dia, lembrar quais foram.
  runningServers: () => request('GET', '/servers'),
  systemMetrics: () => request('GET', '/system/metrics'),
  // O PID vai como identificador para o servidor procurar na última varredura,
  // nunca como ordem: quem decide se aquele processo pode ser encerrado é o
  // servidor, pelo que ele mesmo observou.
  stopProcess: (pid) => request('POST', `/system/processes/${encodeURIComponent(pid)}/stop`),
  serverStatus: (id) => request('GET', `/projects/${encodeURIComponent(id)}/server`),
  startServer: (id) => request('POST', `/projects/${encodeURIComponent(id)}/server/start`),
  stopServer: (id) => request('POST', `/projects/${encodeURIComponent(id)}/server/stop`),
  restartServer: (id) => request('POST', `/projects/${encodeURIComponent(id)}/server/restart`),
  serverLogs: (id, lines = 200) =>
    request('GET', `/projects/${encodeURIComponent(id)}/server/logs`, { params: { lines } }),

  // Ambiente = Docker + aplicação, na ordem. `up` devolve 202 com job_id
  // porque a sequência pode levar minutos; `down` é imediato.
  environmentPlan: (id) => request('GET', `/projects/${encodeURIComponent(id)}/environment`),
  preflight: (id) => request('GET', `/projects/${encodeURIComponent(id)}/environment/preflight`),
  environmentUp: (id, force = false) =>
    request('POST', `/projects/${encodeURIComponent(id)}/environment/up`, {
      params: { force },
    }),
  environmentDown: (id, includeDocker = false) =>
    request('POST', `/projects/${encodeURIComponent(id)}/environment/down`, {
      params: { include_docker: includeDocker ? 'true' : 'false' },
    }),

  dockerStatus: (id) => request('GET', `/projects/${encodeURIComponent(id)}/docker/status`),
  dockerAction: (id, action, services = []) =>
    request('POST', `/projects/${encodeURIComponent(id)}/docker/${action}`, {
      body: { services },
    }),
  dockerLogs: (id, service, tail = 200) =>
    request('GET', `/projects/${encodeURIComponent(id)}/docker/logs`, {
      params: { service, tail },
    }),

  scan: (root, maxDepth) =>
    request('POST', '/discovery/scan', { body: { root, max_depth: maxDepth ?? null } }),
  candidates: (root) => request('GET', '/discovery/candidates', { params: { root } }),
  importCandidates: (paths) => request('POST', '/discovery/import', { body: { paths } }),

  getJob: (id, after = 0) =>
    request('GET', `/jobs/${encodeURIComponent(id)}`, { params: { after } }),
  listJobs: (params) => request('GET', '/jobs', { params }),
  cancelJob: (id) => request('POST', `/jobs/${encodeURIComponent(id)}/cancel`),

  listActivity: (params) => request('GET', '/activity', { params }),
};
