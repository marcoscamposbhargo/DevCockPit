// Roteamento por hash. Recarregar a página mantém a tela (US-013).

const routes = new Map();
let notFoundHandler = null;

export function register(name, pattern, render) {
  routes.set(name, { pattern, render });
}

export function setNotFound(handler) {
  notFoundHandler = handler;
}

export function parseHash(hash) {
  const clean = (hash || '#/dashboard').replace(/^#/, '');
  const [path, queryString] = clean.split('?');
  const segments = path.split('/').filter(Boolean);
  const query = Object.fromEntries(new URLSearchParams(queryString ?? ''));
  return { segments, query };
}

export function resolve(hash) {
  const { segments, query } = parseHash(hash);

  for (const [name, route] of routes) {
    const pattern = route.pattern.split('/').filter(Boolean);
    if (pattern.length !== segments.length) continue;

    const params = {};
    const matched = pattern.every((part, index) => {
      if (part.startsWith(':')) {
        params[part.slice(1)] = decodeURIComponent(segments[index]);
        return true;
      }
      return part === segments[index];
    });

    if (matched) return { name, render: route.render, params, query };
  }

  return null;
}

export function navigate(path) {
  window.location.hash = path.startsWith('#') ? path : `#${path}`;
}

export function start(container, onRouteChange) {
  const handle = async () => {
    const match = resolve(window.location.hash);
    if (!match) {
      if (notFoundHandler) notFoundHandler(container);
      return;
    }
    onRouteChange?.(match);
    await match.render(container, match.params, match.query);
  };

  window.addEventListener('hashchange', handle);
  if (!window.location.hash) window.location.hash = '#/dashboard';
  return handle();
}
