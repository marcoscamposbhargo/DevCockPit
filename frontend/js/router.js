// Roteamento por hash. Recarregar a página mantém a tela (US-013).

const routes = new Map();
let notFoundHandler = null;

//: Trabalho que a tela atual deixou de pé — timer, observador, relógio — e que
//: precisa parar quando ela sair.
//:
//: Existe porque a tela **não sai do DOM**: o `<main id="view">` é o mesmo
//: elemento em todas as rotas, e só o conteúdo dele é trocado. Uma página que
//: se protegia com `container.isConnected` estava perguntando algo que nunca é
//: falso — o timer da tela Ports sobrevivia à navegação e, a cada seis
//: segundos, redesenhava Ports por cima do Dashboard.
const limpezas = [];

/** Registra algo para parar quando a rota mudar. */
export function aoSairDaRota(parar) {
  limpezas.push(parar);
}

function limparRotaAnterior() {
  while (limpezas.length) {
    const parar = limpezas.pop();
    try {
      parar();
    } catch {
      // Limpeza que falha não pode impedir a próxima tela de aparecer.
    }
  }
}

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
    limparRotaAnterior();

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
