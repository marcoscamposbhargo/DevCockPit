// De dado do painel para nós e arestas.
//
// Camada fina de propósito: o grafo não conversa com a API nem com o banco,
// conversa com o que este módulo devolve. Trocar `GET /api/projects` por uma
// rota agregada no futuro mexe só aqui.
//
// Nada aqui inventa relação. Duas coisas só se ligam quando o painel já sabia
// que estavam ligadas.

import { semente } from './layout.js';

//: Tecnologia usada por um projeto só **não vira nó**. Ela não relaciona nada
//: — só empurraria para a tela um satélite por projeto, e o nome dela já
//: aparece no painel lateral. Nó de tecnologia existe para responder "quem
//: mais usa isto aqui?", e essa pergunta começa no segundo projeto.
export const PROJETOS_PARA_VIRAR_NO = 2;

//: Sete dias. Depois disso o projeto continua no grafo, mas para de contar
//: como "mexido recentemente" no tamanho do nó.
const RECENTE_MS = 7 * 24 * 60 * 60 * 1000;

const TAMANHO = { core: 46, projeto: 19, projetoAtivo: 26, projetoFixado: 23, tecnologia: 11 };

function chaveTecnologia(nome) {
  return nome.trim().toLowerCase();
}

/** Matiz da tecnologia, derivada do nome.
 *
 * Não é enfeite: com doze satélites na tela, cor é o que deixa reconhecer
 * "aquele ali é o Docker" sem ler. Sai do hash do nome, então é estável entre
 * sessões e entre máquinas, e é aplicada como **rotação** sobre a cor do token
 * — nenhuma cor literal entra aqui (a regra do `tokens.css` vale para o JS
 * também).
 */
export function matizDaTecnologia(nome) {
  return semente(chaveTecnologia(nome)) % 360;
}

/** Estado do nó de projeto, na mesma doutrina do resto do painel.
 *
 * Duas perguntas diferentes, e o grafo responde à segunda:
 *
 * - `app_running`: **há processo nativo de pé?** É o que o botão de ligar usa,
 *   porque é o que ele liga e desliga.
 * - `app_online`: **a aplicação atende?** Cobre o projeto que roda inteiro em
 *   container, onde o primeiro é falso para sempre.
 *
 * O grafo usava só o primeiro, e desenhava apagado um projeto com os dois
 * containers de pé atendendo — foi o caso do APP INGRESSO. Aqui a pergunta é
 * "está no ar?", não "quem o subiu?".
 *
 * `null` nos dois é `desconhecido`, que a tela desenha diferente de `parado`:
 * projeto sem aplicação separada, ou que ninguém verificou ainda, não é prova
 * de nada.
 */
export function estadoDoProjeto(projeto) {
  if (projeto.app_online === true || projeto.app_running === true) return 'no-ar';
  if (projeto.status === 'ERROR') return 'erro';
  if (projeto.status === 'MISSING') return 'ausente';
  if (projeto.app_online === false || projeto.app_running === false) return 'parado';
  return 'desconhecido';
}

function tamanhoDoProjeto(projeto, agora) {
  if (projeto.app_online === true || projeto.app_running === true) return TAMANHO.projetoAtivo;
  if (projeto.is_pinned) return TAMANHO.projetoFixado;

  const acesso = projeto.last_accessed_at ? Date.parse(projeto.last_accessed_at) : NaN;
  if (!Number.isNaN(acesso) && agora - acesso < RECENTE_MS) return TAMANHO.projetoFixado;

  return TAMANHO.projeto;
}

/**
 * Monta o grafo base: núcleo, projetos e as tecnologias que ligam projetos.
 *
 * @param {Array} projetos itens de `GET /api/projects`
 * @param {number} agora   instante de referência, injetado para o teste não
 *                         depender do relógio da máquina
 */
export function montarGrafo(projetos, { agora = Date.now() } = {}) {
  const nos = [
    {
      id: 'core',
      tipo: 'core',
      rotulo: 'HyperBrain',
      tamanho: TAMANHO.core,
      fixo: true,
    },
  ];
  const arestas = [];

  //: chave normalizada → { rotulo, projetos[] }
  const tecnologias = new Map();

  for (const projeto of projetos) {
    const id = `p:${projeto.id}`;

    nos.push({
      id,
      tipo: 'projeto',
      rotulo: projeto.name,
      tamanho: tamanhoDoProjeto(projeto, agora),
      estado: estadoDoProjeto(projeto),
      fixado: Boolean(projeto.is_pinned),
      projeto,
    });

    arestas.push({ id: `core->${id}`, de: 'core', para: id, kind: 'core' });

    for (const nome of projeto.technologies ?? []) {
      const chave = chaveTecnologia(nome);
      if (!chave) continue;
      if (!tecnologias.has(chave)) tecnologias.set(chave, { rotulo: nome, projetos: [] });
      tecnologias.get(chave).projetos.push(id);
    }
  }

  for (const [chave, tecnologia] of tecnologias) {
    if (tecnologia.projetos.length < PROJETOS_PARA_VIRAR_NO) continue;

    const id = `t:${chave}`;
    nos.push({
      id,
      tipo: 'tecnologia',
      rotulo: tecnologia.rotulo,
      tamanho: TAMANHO.tecnologia,
      matiz: matizDaTecnologia(tecnologia.rotulo),
      // Desenhado pequeno, mas pesado no layout: a tecnologia é o nó com mais
      // ligações e o rótulo mais largo em relação à própria forma. Com peso
      // proporcional ao desenho, os satélites se amontoavam no meio e os
      // nomes se sobrepunham.
      peso: 1.25,
      contagem: tecnologia.projetos.length,
    });

    for (const projetoId of tecnologia.projetos) {
      arestas.push({ id: `${id}->${projetoId}`, de: projetoId, para: id, kind: 'tech' });
    }
  }

  return { nos, arestas };
}

/** Tecnologias do projeto que não viraram nó, para o painel lateral não mentir
 *  por omissão: o grafo mostra as compartilhadas, o painel mostra todas. */
export function tecnologiasExclusivas(projeto, grafo) {
  const compartilhadas = new Set(
    grafo.nos.filter((no) => no.tipo === 'tecnologia').map((no) => no.id.slice(2))
  );
  return (projeto.technologies ?? []).filter((nome) => !compartilhadas.has(chaveTecnologia(nome)));
}

/** Ids dos vizinhos diretos de um nó — a base do modo de foco. */
export function vizinhos(grafo, id) {
  const perto = new Set([id]);
  for (const aresta of grafo.arestas) {
    if (aresta.de === id) perto.add(aresta.para);
    else if (aresta.para === id) perto.add(aresta.de);
  }
  return perto;
}
