// "Mostre os projetos em Python" — resolvido aqui, sem modelo nenhum.
//
// Uma parte grande do que se pergunta a um mapa não é pergunta: é filtro. E
// filtro sobre dado que o navegador já tem em mãos não precisa de IA, não custa
// token e responde em microssegundos. É a mesma doutrina do `orchestrator.py`
// do servidor — **regra primeiro, modelo no empate** —, com uma vantagem: isto
// continua funcionando com o Cockpit AI desligado.
//
// Destacar nó é operação de leitura: não muda nada no sistema, não executa
// nada. Por isso a regra pode decidir sozinha. O que a regra **não** faz é
// adivinhar: frase que não casa critério nenhum devolve `null` e segue seu
// caminho para a IA, em vez de virar um filtro aproximado.

//: Verbo de ação nunca vira filtro de visão. "sobe o kiteasy" tem nome de
//: projeto na frase e casaria com o filtro por nome — e aí a tela destacaria um
//: nó em vez de propor a ação, que é o oposto do pedido.
//: Os verbos destrutivos estão aqui **de propósito**, embora nenhum exista no
//: registro fechado do servidor. Justamente por isso: mandados para lá, voltam
//: como recusa explícita — "não encontrei nenhuma ação do painel que sirva
//: para isso" —, que é a resposta certa para "apaga o banco". Tratados como
//: pergunta, virariam um modelo divagando sobre como apagar um banco.
const ACOES =
  /\b(sobe|subir|suba|liga|ligar|ligue|start|up|desliga|desligar|para|parar|derruba|down|abre|abrir|abra|roda|rodar|reinicia|reiniciar|log|logs|commit|deploy|apaga|apagar|deleta|deletar|remove|remover|exclui|excluir|mata|matar|limpa|limpar|dropa|reseta|resetar|publica|publicar)\b/;

//: Pergunta de verdade nunca vira filtro. "por que o python do smartdash está
//: lento?" cita uma tecnologia, mas quem escreveu quer resposta, não destaque.
//: Este veto vem antes de qualquer critério.
const PERGUNTAS =
  /\b(por\s*que|porque|por\s*qual|como|qual\s+o\s+motivo|explica\w*|o\s+que\s+e|o\s+que\s+sao|serve\s+para|deveria|devo)\b/;

//: Frase longa só vira filtro se pedir explicitamente para ver.
const GATILHOS =
  /\b(mostr\w*|quais|projetos?|quem\s+usa|quem\s+tem|destaq\w*|filtr\w*|list\w*|onde|todos\s+os|todas\s+as|o\s+que\s+esta|quais\s+estao|quem\s+esta)\b/;

const PALAVRAS_PARA_DISPENSAR_GATILHO = 3;

/** A frase soa como ordem — vale perguntar ao servidor se existe ação para ela.
 *
 * Existe por causa do relógio. Pedir proposta é barato quando a regra do
 * servidor decide (0,2 s), e caro quando ela não decide: aí entra o modelo, e
 * num provedor local isso custa de 15 a 40 segundos **antes** de a pergunta
 * sequer começar a ser respondida. "Onde paramos ontem?" não é ordem, e não
 * deveria pagar esse pedágio.
 *
 * O julgamento aqui é só sobre *perguntar ou não perguntar*: quem decide se a
 * ação existe, e qual é, continua sendo o servidor, com o registro fechado.
 */
export function pareceOrdem(texto) {
  return ACOES.test(normalizar(texto));
}

export function normalizar(texto) {
  return String(texto ?? '')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .trim();
}

const CRITERIOS = [
  {
    chave: 'no-ar',
    rotulo: 'no ar',
    padrao: /\b(no ar|rodando|ligad[oa]s?|online|de pe)\b/,
    casa: (projeto) => projeto.app_running === true,
  },
  {
    chave: 'parado',
    rotulo: 'parados',
    padrao: /\b(parad[oa]s?|desligad[oa]s?|offline)\b/,
    casa: (projeto) => projeto.app_running === false,
  },
  {
    chave: 'fixado',
    rotulo: 'fixados',
    padrao: /\b(fixad[oa]s?|favorit[oa]s?)\b/,
    casa: (projeto) => Boolean(projeto.is_pinned),
  },
  {
    chave: 'recente',
    rotulo: 'mexidos nos últimos 7 dias',
    padrao: /\b(recente|recentes|hoje|essa semana|esta semana|ultimos dias|ultimamente|mexi)\b/,
    casa: (projeto, { agora }) => {
      if (!projeto.last_accessed_at) return false;
      const quando = Date.parse(projeto.last_accessed_at);
      return !Number.isNaN(quando) && agora - quando < 7 * 24 * 60 * 60 * 1000;
    },
  },
  {
    chave: 'sem-ia',
    rotulo: 'fora do Cockpit AI',
    padrao: /\b(fora da ia|sem ia|excluid[oa]s? da ia)\b/,
    casa: (projeto) => projeto.ai_enabled === false,
  },
];

/** Tecnologias citadas na frase, das que existem nos projetos. */
function tecnologiasCitadas(frase, projetos) {
  const nomes = new Set();
  for (const projeto of projetos) {
    for (const tecnologia of projeto.technologies ?? []) nomes.add(tecnologia);
  }

  // Do nome mais longo para o mais curto, e o mais curto é descartado quando
  // já está dentro de um que casou: "docker-compose" casa "docker" junto, e
  // exigir as duas transformaria a frase num filtro que quase nunca casa.
  const casados = [];

  for (const nome of [...nomes].sort((a, b) => b.length - a.length)) {
    const alvo = normalizar(nome);
    if (!alvo) continue;
    const escapado = alvo.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    if (!new RegExp(`(^|[^a-z0-9])${escapado}([^a-z0-9]|$)`).test(frase)) continue;
    if (casados.some((maior) => normalizar(maior).includes(alvo))) continue;
    casados.push(nome);
  }

  return casados;
}

/**
 * Da frase para um filtro de visão — ou `null`, quando não é filtro.
 *
 * @param {string} texto     o que a pessoa escreveu
 * @param {Array}  projetos  itens de `GET /api/projects`
 * @returns {{rotulo: string, ids: Set<string>, total: number}|null}
 */
export function interpretar(texto, projetos, { agora = Date.now() } = {}) {
  const frase = normalizar(texto);
  if (!frase) return null;
  if (ACOES.test(frase)) return null;
  if (PERGUNTAS.test(frase)) return null;

  const palavras = frase.split(/\s+/).filter(Boolean).length;
  const pediuParaVer = GATILHOS.test(frase) || palavras <= PALAVRAS_PARA_DISPENSAR_GATILHO;
  if (!pediuParaVer) return null;

  const criterios = CRITERIOS.filter((criterio) => criterio.padrao.test(frase));
  const tecnologias = tecnologiasCitadas(frase, projetos);

  if (!criterios.length && !tecnologias.length) return null;

  const alvos = projetos.filter((projeto) => {
    const passaCriterios = criterios.every((criterio) => criterio.casa(projeto, { agora }));
    const declaradas = new Set((projeto.technologies ?? []).map(normalizar));
    const passaTecnologias = tecnologias.every((nome) => declaradas.has(normalizar(nome)));
    return passaCriterios && passaTecnologias;
  });

  const partes = [...tecnologias, ...criterios.map((criterio) => criterio.rotulo)];

  return {
    rotulo: partes.join(' · '),
    // O nó de tecnologia entra no destaque junto: ele é a resposta visual de
    // "quem mais usa isto aqui?".
    ids: new Set([
      'core',
      ...alvos.map((projeto) => `p:${projeto.id}`),
      ...tecnologias.map((nome) => `t:${normalizar(nome)}`),
    ]),
    total: alvos.length,
  };
}
