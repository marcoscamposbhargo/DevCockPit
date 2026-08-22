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

async function request(method, path, { body, params } = {}) {
  const url = new URL(BASE + path, window.location.origin);
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.set(key, String(value));
    }
  }

  const headers = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (method !== 'GET') headers['X-DevCockpit-Client'] = 'web';

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

  dashboard: () => request('GET', '/dashboard'),

  listServices: (id) => request('GET', `/projects/${encodeURIComponent(id)}/services`),
  checkServices: (id) => request('POST', `/projects/${encodeURIComponent(id)}/services/check`),
  ports: () => request('GET', '/services/ports'),

  openVsCode: (id) => request('POST', `/projects/${encodeURIComponent(id)}/open/vscode`),
  openFolder: (id) => request('POST', `/projects/${encodeURIComponent(id)}/open/folder`),
  openTerminal: (id) => request('POST', `/projects/${encodeURIComponent(id)}/open/terminal`),
  openBrowser: (id, serviceKey) =>
    request('POST', `/projects/${encodeURIComponent(id)}/open/browser`, {
      body: { service_key: serviceKey },
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
