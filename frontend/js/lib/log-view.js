// Visor de log: o fim de um arquivo, atualizado enquanto se olha.
//
// Diferente do `job-console.js`, que acompanha um job do começo ao fim e
// termina. Aqui não há fim: o servidor de desenvolvimento fica de pé, e o
// arquivo continua crescendo. O visor busca as últimas linhas de tempos em
// tempos e substitui o que mostra.
//
// **Por que polling e não stream.** O backend lê o fim do arquivo sob demanda;
// não há SSE para log de servidor. Fazer um custaria acompanhar o arquivo no
// servidor, e o ganho seria o atraso cair de um segundo para zero — num texto
// que a pessoa lê em dezenas de segundos. O `job-console` já cai para polling
// quando o SSE quebra, e ali funciona bem.
//
// **Por que substituir em vez de anexar.** A fonte é "as últimas N linhas",
// não "o que mudou desde a última vez". Tentar deduzir o delta comparando
// textos erraria em toda linha repetida — e log de servidor repete muito
// ("Reloading...", "GET / 200"). Substituir é honesto e mais simples; o preço é
// redesenhar um bloco de texto por segundo, que o navegador nem sente.

import { el } from './dom.js';

const INTERVALO_MS = 1000;

/**
 * @param {object} options
 * @param {Function} options.fetchLines  devolve Promise<string[]>
 * @param {string}   options.vazio       texto quando não há linha alguma
 * @param {boolean}  options.ativo       começa buscando?
 */
export function logView({ fetchLines, vazio = 'Sem saída ainda.', ativo = true } = {}) {
  let autoscroll = true;
  let timer = 0;
  let ultimoTexto = null;
  let parado = false;

  const saida = el('pre', {
    class: 'log-view__output',
    tabindex: '0',
    // O log é uma região que muda sozinha; sem isto o leitor de tela anunciaria
    // cada atualização, o que num servidor em watch seria insuportável.
    'aria-live': 'off',
    role: 'log',
  });

  const marca = el('span', { class: 'log-view__status', text: ativo ? 'ao vivo' : 'parado' });

  const autoscrollBtn = el('button', {
    class: 'btn btn--sm',
    type: 'button',
    text: 'Autoscroll: on',
    onClick: () => {
      autoscroll = !autoscroll;
      autoscrollBtn.textContent = `Autoscroll: ${autoscroll ? 'on' : 'off'}`;
      if (autoscroll) saida.scrollTop = saida.scrollHeight;
    },
  });

  // Rolar para cima pausa o autoscroll: é o que a pessoa quis dizer ao rolar.
  saida.addEventListener('scroll', () => {
    const noFim = saida.scrollHeight - saida.scrollTop - saida.clientHeight < 24;
    if (!noFim && autoscroll) {
      autoscroll = false;
      autoscrollBtn.textContent = 'Autoscroll: off';
    }
  });

  const desenhar = (linhas) => {
    const texto = linhas.join('\n');
    // Só toca no DOM quando mudou: sem isto, cada volta do relógio destruiria a
    // seleção de texto de quem estivesse copiando uma linha de erro.
    if (texto === ultimoTexto) return;
    ultimoTexto = texto;

    saida.replaceChildren(document.createTextNode(texto || vazio));
    saida.dataset.vazio = linhas.length ? 'false' : 'true';
    if (autoscroll) saida.scrollTop = saida.scrollHeight;
  };

  const buscar = async () => {
    if (parado) return;
    try {
      desenhar(await fetchLines());
      marca.textContent = 'ao vivo';
      marca.dataset.erro = 'false';
    } catch {
      // Servidor do painel fora do ar, ou projeto removido. O texto que já
      // está na tela continua valendo — é a última verdade conhecida.
      marca.textContent = 'sem atualizar';
      marca.dataset.erro = 'true';
    }
  };

  const raiz = el('section', { class: 'log-view' }, [
    el('header', { class: 'log-view__header' }, [
      marca,
      el('span', { style: 'margin-left:auto' }, [autoscrollBtn]),
    ]),
    saida,
  ]);

  const parar = () => {
    parado = true;
    if (timer) {
      window.clearInterval(timer);
      timer = 0;
    }
  };

  const comecar = () => {
    parado = false;
    buscar();
    if (!timer) timer = window.setInterval(buscar, INTERVALO_MS);
  };

  if (ativo) comecar();
  else desenhar([]);

  return { element: raiz, parar, comecar, atualizar: buscar };
}
