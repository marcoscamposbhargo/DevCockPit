// DOM mínimo para rodar os módulos do painel fora do navegador.
//
// Não é jsdom, e é de propósito: o frontend deste projeto não tem uma única
// dependência nem passo de build (ADR-005), e trazer node_modules só para
// testar contradiria a decisão que faz o painel ser servido como arquivo
// estático. O que os módulos usam é pouco e estável — `createElement`,
// `dataset`, eventos e `append` —, então o dublê cabe num arquivo.
//
// O que ele **não** finge: layout, CSS, foco, seleção. Teste que precisar
// disso é teste de navegador, e este não é o lugar.

export class FakeNode {
  constructor(tag) {
    this.tag = tag;
    this.children = [];
    this.attrs = {};
    this.dataset = {};
    this.text = '';
    this.listeners = new Map();
    this.hidden = false;
    this.disabled = false;
  }

  set className(valor) {
    this.attrs.class = valor;
  }

  get className() {
    return this.attrs.class ?? '';
  }

  set textContent(valor) {
    this.text = String(valor);
    this.children = [];
  }

  get textContent() {
    return this.text + this.children.map((filho) => filho.textContent ?? '').join('');
  }

  setAttribute(chave, valor) {
    this.attrs[chave] = String(valor);
  }

  getAttribute(chave) {
    return this.attrs[chave] ?? null;
  }

  addEventListener(tipo, fn) {
    if (!this.listeners.has(tipo)) this.listeners.set(tipo, []);
    this.listeners.get(tipo).push(fn);
  }

  /** Dispara um evento neste nó. Sem propagação: nada aqui depende dela. */
  emit(tipo, evento = {}) {
    for (const fn of this.listeners.get(tipo) ?? []) fn(evento);
  }

  append(...nós) {
    this.children.push(...nós);
  }

  get firstChild() {
    return this.children[0] ?? null;
  }

  removeChild(no) {
    this.children = this.children.filter((filho) => filho !== no);
  }

  /** Todos os descendentes, incluindo este nó. Só o que os testes precisam. */
  *walk() {
    yield this;
    for (const filho of this.children) {
      if (filho instanceof FakeNode) yield* filho.walk();
    }
  }

  /** Nós cuja classe contém o nome dado. */
  findByClass(nome) {
    return [...this.walk()].filter((no) => (no.className || '').split(/\s+/).includes(nome));
  }

  /** Textos de todos os descendentes, em ordem. */
  texts() {
    return [...this.walk()].map((no) => no.text).filter(Boolean);
  }
}

/** Instala `document` e `window` globais. Devolve utilidades do relógio. */
export function instalarDom({ hash = '#/dashboard' } = {}) {
  globalThis.Node = FakeNode;
  globalThis.document = {
    createElement: (tag) => new FakeNode(tag),
    createElementNS: (_ns, tag) => new FakeNode(tag),
    createTextNode: (texto) => Object.assign(new FakeNode('#text'), { text: String(texto) }),
    visibilityState: 'visible',
  };

  const ouvintes = new Map();
  const timers = new Map();
  let proximoTimer = 1;

  globalThis.window = {
    location: { hash, origin: 'http://127.0.0.1:8765' },
    localStorage: { getItem: () => null, setItem: () => {} },
    addEventListener: (tipo, fn) => {
      if (!ouvintes.has(tipo)) ouvintes.set(tipo, []);
      ouvintes.get(tipo).push(fn);
    },
    setInterval: (fn, ms) => {
      const id = proximoTimer++;
      timers.set(id, { fn, ms });
      return id;
    },
    clearInterval: (id) => timers.delete(id),
    setTimeout: (fn) => {
      const id = proximoTimer++;
      timers.set(id, { fn, ms: 0 });
      return id;
    },
  };

  return {
    /** Simula a navegação: troca o hash e dispara `hashchange`. */
    async navegar(novo) {
      globalThis.window.location.hash = novo;
      for (const fn of ouvintes.get('hashchange') ?? []) await fn();
    },
    /** Quantos timers seguem armados — é como se prova que a limpeza rodou. */
    timersVivos: () => timers.size,
    /** Executa o callback de todos os timers, uma vez. */
    dispararTimers: () => {
      for (const { fn } of [...timers.values()]) fn();
    },
  };
}
