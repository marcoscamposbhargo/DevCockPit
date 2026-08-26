// Estado visual do grafo — e só o visual.
//
// Nó selecionado, nó em foco, destaque, estado do núcleo: tudo isto morre com
// a tela e **nunca** vai para o banco. Estado de visualização virando dado
// persistido é como um grafo vira, sem ninguém decidir, um segundo gerenciador
// de projetos ao lado do que já existe.
//
// A única exceção é a preferência de movimento, que é escolha da pessoa e não
// do grafo — e por isso vive no `localStorage`, junto do tema.

const CHAVE_MOVIMENTO = 'devcockpit:hyperbrain:movimento';

/** A pessoa pediu menos movimento, aqui ou no sistema operacional. */
export function movimentoReduzido() {
  try {
    const salvo = window.localStorage.getItem(CHAVE_MOVIMENTO);
    if (salvo === 'reduzido') return true;
    if (salvo === 'completo') return false;
  } catch {
    // localStorage bloqueado não pode impedir a tela de abrir.
  }
  return Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches);
}

export function definirMovimento(reduzido) {
  try {
    window.localStorage.setItem(CHAVE_MOVIMENTO, reduzido ? 'reduzido' : 'completo');
  } catch {
    // Preferência que não persiste ainda vale para esta sessão.
  }
}

export function criarEstado() {
  const valores = {
    //: Nó clicado. Abre o painel lateral.
    selecionado: null,
    //: Nó em modo de foco: ele e os vizinhos ficam nítidos, o resto atenua.
    foco: null,
    //: Conjunto de ids em destaque, ou `null` quando não há filtro ativo.
    destacados: null,
    //: idle | listening | thinking | accessing | executing | success | warning | error
    cerebro: 'idle',
  };

  const ouvintes = new Set();

  return {
    get: (chave) => valores[chave],
    definir(mudancas) {
      let mudou = false;
      for (const [chave, valor] of Object.entries(mudancas)) {
        if (valores[chave] === valor) continue;
        valores[chave] = valor;
        mudou = true;
      }
      if (mudou) for (const ouvinte of ouvintes) ouvinte(valores);
    },
    aoMudar(ouvinte) {
      ouvintes.add(ouvinte);
      return () => ouvintes.delete(ouvinte);
    },
  };
}
