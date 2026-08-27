// Comandos de barra — Fase 3.5.
//
// O que um comando **é** aqui: um atalho para uma frase que você digitaria de
// qualquer jeito, com o especialista certo já escolhido. `/find-bugs` não abre
// uma capacidade nova; ele economiza a digitação e tira a dúvida de qual chapéu
// pediria aquilo.
//
// Nada aqui executa. Comando vira pergunta com perfil fixado, e segue o mesmo
// caminho de sempre: contexto montado no servidor, resposta em stream, ação só
// por proposta confirmada.
//
// Módulo puro, sem DOM: dá para testar no runner do Node.

/** @typedef {{nome: string, resumo: string, agente: string, frase: string}} Comando */

/** @type {Comando[]} */
export const COMANDOS = [
  {
    nome: '/status',
    resumo: 'onde este projeto está agora',
    agente: 'devops',
    frase:
      'Resuma o estado atual deste projeto: o que está no ar, o que está parado, ' +
      'e o que chama atenção no que o painel mediu.',
  },
  {
    nome: '/plan',
    resumo: 'o que fazer em seguida',
    agente: 'fullstack',
    frase:
      'A partir da última sessão, das tarefas abertas e do próximo passo declarado, ' +
      'proponha o que fazer agora. Uma coisa por vez, na ordem, com o motivo.',
  },
  {
    nome: '/find-bugs',
    resumo: 'o que parece quebrado',
    agente: 'qa',
    frase:
      'Olhando o que o painel registrou — falhas, ações recusadas, servidor que ' +
      'caiu, bugs anotados na memória —, o que parece quebrado neste projeto?',
  },
  {
    nome: '/why',
    resumo: 'por que não sobe',
    agente: 'devops',
    frase:
      'Este projeto não sobe. Com base em porta, container, dependência e log, ' +
      'liste as causas prováveis em ordem, e o que verificar primeiro.',
  },
  {
    nome: '/review',
    resumo: 'revisar o que mudou',
    agente: 'fullstack',
    frase:
      'A partir das alterações sem commit e dos últimos commits, revise o que ' +
      'mudou: o que merece atenção antes de continuar.',
  },
  {
    nome: '/document',
    resumo: 'o que falta documentar',
    agente: 'fullstack',
    frase:
      'O que este projeto tem de importante e não está escrito em lugar nenhum? ' +
      'Considere README, decisões e o que a memória do projeto guarda.',
  },
];

const POR_NOME = new Map(COMANDOS.map((c) => [c.nome, c]));

/** O que a pessoa digitou é um comando? Devolve a pergunta a enviar, ou `null`.
 *
 * Aceita argumento depois do comando (`/why o banco`): ele entra como
 * complemento da frase, porque quem digitou tinha algo específico em mente e
 * jogar isso fora seria pior que não ter comando nenhum.
 */
export function interpretarComando(entrada) {
  const texto = String(entrada ?? '').trim();
  if (!texto.startsWith('/')) return null;

  const [nome, ...resto] = texto.split(/\s+/);
  const comando = POR_NOME.get(nome.toLowerCase());
  if (!comando) return null;

  const complemento = resto.join(' ').trim();

  return {
    comando,
    agente: comando.agente,
    pergunta: complemento ? `${comando.frase}\n\nEm especial: ${complemento}` : comando.frase,
  };
}

/** Comandos que casam com o que está sendo digitado, para a lista de sugestão. */
export function sugerir(entrada) {
  const texto = String(entrada ?? '').trim().toLowerCase();
  if (!texto.startsWith('/')) return [];

  const [nome] = texto.split(/\s+/);
  // Comando inteiro já digitado: a lista sai da frente em vez de cobrir o campo.
  if (POR_NOME.has(nome) && texto.length > nome.length) return [];

  return COMANDOS.filter((c) => c.nome.startsWith(nome));
}
