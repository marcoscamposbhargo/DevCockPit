// Mapa de portas: quem declara o quê, onde bate, e a troca do número.
//
// Vinte projetos locais brigam por 3000, 5173 e 8000 mais cedo ou mais tarde.
// Até aqui o DevCockpit só sabia *avisar* do conflito no dashboard; resolver
// exigia abrir o `.env` de cada projeto e lembrar quem já tinha usado o quê.
//
// O que esta tela troca é a porta **declarada no registro do DevCockpit** —
// o que ele usa para verificar o serviço e para abrir o navegador. Ela não
// edita arquivo de projeto nenhum: o `.env`, o Compose e o `vite.config` são
// do projeto, e uma ferramenta de painel não reescreve fonte alheia sem ser
// mandada. O aviso na tela diz isso na cara, para ninguém trocar aqui e achar
// que o servidor mudou de porta sozinho.

import { api } from '../lib/api.js';
import { el, mount } from '../lib/dom.js';
import { icon } from '../lib/icons.js';
import { emptyState, pageHeader, showError, skeletonGrid, toast } from '../lib/ui.js';
import { aoSairDaRota, navigate } from '../router.js';

const PORTA_MIN = 1;
const PORTA_MAX = 65535;
//: De quanto em quanto tempo a tela relê o mapa. Metade do que esta tela
//: mostra é estado vivo — quem está escutando agora, qual servidor caiu —, e
//: uma tela de estado vivo que só muda quando se aperta um botão é uma tela
//: que mente entre um aperto e outro. O poller do servidor já mantém a
//: observação fresca; aqui só se busca o que ele já apurou.
const RECARGA_MS = 6000;
//: De onde a sugestão de porta livre começa a procurar. Abaixo de 1024 é
//: território de porta privilegiada; entre 1024 e 3000 mora meio mundo
//: (MySQL, Postgres, Redis) que não declara nada no DevCockpit.
const SUGESTAO_INICIO = 3000;

/** Troca a porta dentro de uma URL local, preservando o resto.
 *
 * `URL` normaliza `http://localhost:3000` para `.../`; devolver a barra a mais
 * mudaria o endereço que a pessoa cadastrou sem ela ter pedido. */
function comPorta(url, porta) {
  if (!url) return url;
  try {
    const alvo = new URL(url);
    alvo.port = String(porta);
    const texto = alvo.toString();
    return texto.endsWith('/') && !url.endsWith('/') ? texto.slice(0, -1) : texto;
  } catch {
    // URL que não parseia fica como está: melhor um endereço velho visível do
    // que um endereço corrompido por regex.
    return url;
  }
}

/** A menor porta que ninguém declarou **e** ninguém está escutando.
 *
 * As duas condições, não uma. Considerar só o que os projetos declaram fazia a
 * sugestão cair em cima de um Postgres nativo ou de um container de outro
 * projeto — números que o DevCockpit não conhece e a máquina conhece muito
 * bem. Quem clica em "Sugerir livre" espera uma porta livre; entregar uma
 * ocupada troca um conflito conhecido por um conflito que só aparece no
 * próximo `up`. */
function proximaLivre(ocupadas, escutando, apartir = SUGESTAO_INICIO) {
  let porta = apartir;
  while (porta < PORTA_MAX && (ocupadas.has(porta) || escutando.has(porta))) porta += 1;
  return porta;
}

function conflictAlert(mapa) {
  const conflitos = mapa.items.filter((item) => item.conflict);
  if (!conflitos.length) return null;

  return el('div', { class: 'alert', role: 'status' }, [
    el('span', { class: 'alert__icon' }, [icon('alert', { size: 16 })]),
    el('div', { class: 'alert__body' }, [
      el('strong', {
        text:
          conflitos.length === 1
            ? '1 porta declarada por mais de um serviço'
            : `${conflitos.length} portas declaradas por mais de um serviço`,
      }),
      el('p', {
        class: 'field__hint',
        text:
          'Só um consegue escutar por vez. Troque a porta de quem ceder — ' +
          'e lembre de trocar também no arquivo do projeto.',
      }),
      ...conflitos.map((item) =>
        el('div', { class: 'field__hint' }, [
          el('span', { class: 'mono', text: String(item.port) }),
          ` · ${item.projects.join(', ')}`,
        ])
      ),
    ]),
  ]);
}

/** Aviso de divergência: o declarado não é o que está no ar.
 *
 * É o aviso mais útil desta tela e o único que o painel não sabia dar. Um
 * número velho no cadastro fazia o projeto aparecer parado com o servidor
 * rodando — e depois de ver isso duas vezes ninguém mais acredita na coluna de
 * estado. O botão aplica a porta observada de uma vez, porque a correção é
 * sempre a mesma e digitar o número de novo é atrito puro.
 */
function mismatchAlert(mapa, { onAdotar, onEditarPorta }) {
  if (!mapa.mismatches?.length) return null;

  return el('div', { class: 'alert', role: 'status' }, [
    el('span', { class: 'alert__icon' }, [icon('alert', { size: 16 })]),
    el('div', { class: 'alert__body' }, [
      el('strong', {
        text:
          mapa.mismatches.length === 1
            ? '1 serviço está no ar em outra porta'
            : `${mapa.mismatches.length} serviços estão no ar em outra porta`,
      }),
      el('p', {
        class: 'field__hint',
        text:
          'O projeto tem processo escutando, só que não na porta cadastrada. ' +
          'Enquanto os dois números não baterem, o painel mostra o serviço como desligado.',
      }),
      ...mapa.mismatches.map((divergencia) =>
        el('div', { class: 'mismatch-row' }, [
          el('span', { text: `${divergencia.project_name} · ${divergencia.service_label}` }),
          el('span', { class: 'mono', text: `declarado ${divergencia.declared_port}` }),
          divergencia.observed_port
            ? el('span', { class: 'mono mismatch-row__real' }, [
                icon('plug', { size: 12 }),
                `no ar em ${divergencia.observed_port}`,
                divergencia.process_name
                  ? el('span', { class: 'field__hint', text: ` (${divergencia.process_name})` })
                  : null,
              ])
            : // Sem sugestão o aviso continua valendo — o número está errado —,
              // mas quem escolhe o certo é quem conhece o projeto. Oferecer um
              // botão que chuta custaria uma porta trocada à toa.
              el('span', { class: 'field__hint', text: 'nada do projeto responde nessa porta' }),
          divergencia.observed_port
            ? el('button', {
                class: 'btn btn--sm btn--primary',
                type: 'button',
                text: `Usar ${divergencia.observed_port}`,
                title: 'Grava a porta observada no cadastro deste serviço.',
                onClick: () => onAdotar(divergencia),
              })
            : el('button', {
                class: 'btn btn--sm',
                type: 'button',
                text: 'Corrigir',
                title: 'Abre a edição da porta deste serviço na tabela abaixo.',
                onClick: () => onEditarPorta(divergencia),
              }),
        ])
      ),
    ]),
  ]);
}

/** Servidores de desenvolvimento largados, com a opção de encerrar.
 *
 * Estes estavam escondidos. Iam para o mesmo acordeão recolhido das trinta e
 * cinco portas de sistema — junto de `svchost`, `Discord` e `AnyDesk` —, e o
 * sinal que importa sumia no ruído: um `node.exe` de um projeto que já foi
 * removido do painel, segurando a porta 3000 indefinidamente, sem nenhum
 * caminho de volta pela interface.
 *
 * Só entra aqui o que roda **dentro de um root permitido**. É a mesma defesa
 * que limita onde um projeto pode ser cadastrado, reusada para limitar o que
 * pode ser encerrado: o resto da máquina fica fora de alcance por construção, e
 * não por uma lista de exceções que alguém precisaria manter.
 */
/** `C:/Users/.../Projetos/AI Procedures` -> `…/Projetos/AI Procedures`.
 *
 * As duas barras na classe: o caminho chega do Windows com `\`, e o corte
 * precisa funcionar dos dois lados. */
function caminhoCurto(cwd) {
  if (!cwd) return 'origem desconhecida';
  const partes = String(cwd).split(/[\\/]/).filter(Boolean);
  return partes.length > 2 ? `…/${partes.slice(-2).join('/')}` : cwd;
}

/** Processos de projeto que o painel não subiu — e por isso não sabe parar.
 *
 * Veio do Dashdate: um `uvicorn` deixado num terminal, na porta que o projeto
 * declara. "Desligar" no card encerra o que o painel iniciou, e esse não foi;
 * o clique respondia sucesso e o projeto seguia no ar. Nenhuma tela oferecia
 * outro caminho, então a conclusão razoável era que o botão não funcionava.
 *
 * Separado dos órfãos de propósito: são situações diferentes para quem lê. O
 * órfão perdeu o projeto; este tem dono, só não passou pelo painel.
 */
function unmanagedSection(mapa, { onEncerrar }) {
  const soltos = (mapa.observed ?? []).filter((porta) => porta.unmanaged);
  if (!soltos.length) return null;

  return el('div', { class: 'alert', role: 'status' }, [
    el('span', { class: 'alert__icon' }, [icon('alert', { size: 16 })]),
    el('div', { class: 'alert__body' }, [
      el('strong', {
        text:
          soltos.length === 1
            ? '1 processo de projeto que o painel não subiu'
            : `${soltos.length} processos de projeto que o painel não subiu`,
      }),
      el('p', {
        class: 'field__hint',
        text:
          'Está na porta que o projeto declara, mas foi iniciado por fora — ' +
          'num terminal, ou numa sessão anterior. "Desligar" no card não ' +
          'alcança esses: ele encerra o que o painel iniciou.',
      }),
      ...soltos.map((porta) => {
        const botao = el('button', {
          class: 'btn btn--sm btn--danger',
          type: 'button',
          text: 'Encerrar',
        });
        botao.addEventListener('click', () => onEncerrar(porta, botao));

        return el('div', { class: 'mismatch-row' }, [
          el('span', { class: 'mono', text: `porta ${porta.port}` }),
          el('span', { text: porta.project_name ?? 'projeto desconhecido' }),
          el('span', {
            class: 'field__hint mono',
            text: `${porta.process_name ?? 'processo'} · ${caminhoCurto(porta.cwd)}`,
            title: porta.cwd ?? '',
          }),
          botao,
        ]);
      }),
    ]),
  ]);
}

function orphanSection(mapa, { onEncerrar }) {
  const orfaos = (mapa.observed ?? []).filter((porta) => porta.orphan);
  if (!orfaos.length) return null;

  return el('div', { class: 'alert alert--orfaos', role: 'status' }, [
    el('span', { class: 'alert__icon' }, [icon('alert', { size: 16 })]),
    el('div', { class: 'alert__body' }, [
      el('strong', {
        text:
          orfaos.length === 1
            ? '1 servidor de desenvolvimento sem projeto'
            : `${orfaos.length} servidores de desenvolvimento sem projeto`,
      }),
      el('p', {
        class: 'field__hint',
        text:
          'Rodando dentro dos seus diretórios de trabalho, mas nenhum projeto ' +
          'cadastrado o reivindica. Costuma ser servidor que sobreviveu à ' +
          'remoção do projeto e ficou segurando a porta.',
      }),
      ...orfaos.map((porta) => {
        const botao = el('button', {
          class: 'btn btn--sm btn--danger',
          type: 'button',
          text: 'Encerrar',
        });
        botao.addEventListener('click', () => onEncerrar(porta, botao));

        return el('div', { class: 'mismatch-row' }, [
          el('span', { class: 'mono', text: `porta ${porta.port}` }),
          el('span', { text: porta.process_name ?? 'processo' }),
          el('span', {
            class: 'field__hint mono',
            text: caminhoCurto(porta.cwd),
            title: porta.cwd ?? '',
          }),
          el('a', {
            class: 'field__hint',
            href: `http://localhost:${porta.port}`,
            target: '_blank',
            rel: 'noreferrer',
            text: 'ver',
            title: 'Abrir para conferir o que é antes de encerrar.',
          }),
          botao,
        ]);
      }),
    ]),
  ]);
}

/** Portas em escuta que nenhum serviço cadastrado declara.
 *
 * Responde a pergunta que aparece quando um `up` falha com "address already in
 * use": quem está com a porta. Sem esta lista a resposta exigia `netstat` num
 * terminal à parte.
 *
 * Recolhida de propósito: aqui mora o ruído da máquina — `svchost`, Discord,
 * AnyDesk. O que tem ação vai para a seção de órfãos, em destaque.
 */
function unclaimedSection(mapa, { aberto = false, onToggle = () => {} } = {}) {
  if (!mapa.observation_available) {
    return el('p', { class: 'field__hint', style: 'margin-top:var(--sp-4)' }, [
      'Não foi possível ler as portas em escuta nesta máquina. ',
      'O mapa acima mostra só o que os projetos declaram.',
    ]);
  }

  const declaradas = new Set(mapa.bindings.map((b) => b.port));
  // Órfão tem seção própria, em destaque. Repetir aqui faria a mesma porta
  // aparecer duas vezes na tela, e a de cima é a que tem o que fazer.
  const sobrando = (mapa.observed ?? []).filter(
    (p) => !declaradas.has(p.port) && !p.orphan
  );
  if (!sobrando.length) return null;

  const rotulo = (porta) => {
    if (porta.project_name) return `${porta.project_name} (não declarada)`;
    if (porta.matched_by === 'container') return 'publicada por container';
    return porta.process_name ?? 'processo desconhecido';
  };

  // Ordenado por número. A ordem de chegada do scanner é a do sistema
  // operacional, que não é ordem nenhuma — e quem abre esta lista veio
  // procurar um número específico.
  const ordenadas = [...sobrando].sort((a, b) => a.port - b.port);

  const bloco = el('details', { class: 'ports-unclaimed' }, [
    el('summary', {
      text: `${sobrando.length} porta(s) em escuta que nenhum serviço declara`,
    }),
    el('p', {
      class: 'field__hint',
      text: 'Útil quando o Compose falha com "address already in use".',
    }),
    el(
      'ul',
      { class: 'ports-unclaimed__list' },
      ordenadas.map((porta) =>
        el('li', {}, [
          el('span', { class: 'mono', text: String(porta.port) }),
          ' · ',
          rotulo(porta),
          // O que faltava para a lista responder à pergunta que ela existe
          // para responder. "processo desconhecido" não diz de quem é a porta;
          // o pid e o diretório dizem, e são o que se leva para o gerenciador
          // de tarefas quando a resposta é matar.
          porta.pid ? el('span', { class: 'field__hint mono', text: `pid ${porta.pid}` }) : null,
          porta.cwd
            ? el('span', {
                class: 'field__hint mono',
                text: caminhoCurto(porta.cwd),
                title: porta.cwd,
              })
            : null,
        ])
      )
    ),
  ]);

  bloco.open = aberto;
  bloco.addEventListener('toggle', () => onToggle(bloco.open));

  return bloco;
}

/** Linha em modo leitura. */
function bindingRow(binding, { onEdit, noAr }) {
  const endereco = binding.url ?? `${binding.host}:${binding.port}`;

  return el('tr', { dataset: { conflict: String(binding.conflict) } }, [
    el('td', { class: 'mono' }, [
      // O flex fica num `span` dentro da célula: aplicá-lo na própria `td`
      // tira a célula do layout de tabela e desalinha a linha inteira.
      el('span', { class: 'port-cell' }, [
        String(binding.port),
        binding.conflict
          ? el('span', { class: 'port-flag', title: 'Outro serviço declara esta mesma porta.' }, [
              icon('alert', { size: 12 }),
              'conflito',
            ])
          : null,
        // Confirmação de que o número não é só declaração: alguém escuta ali.
        // Duas marcas, porque são duas afirmações diferentes.
        //
        // "no ar" diz **este serviço está de pé**, e isso exige prova: o
        // processo roda dentro do diretório do projeto. "ocupada" diz só que
        // alguém está na porta, sem afirmar quem.
        //
        // A distinção nasceu de um caso real: a 8000 estava com um container da
        // PLATAFORMA, e o painel a atribuiu ao SmartDash porque só ele
        // declarava 8000. A tela dizia "SmartDash Backend no ar" apontando para
        // o servidor de outro projeto, com o do SmartDash morto.
        noAr?.forte
          ? el('span', { class: 'port-flag port-flag--live', title: noAr.texto }, [
              icon('plug', { size: 12 }),
              'no ar',
            ])
          : noAr
            ? el('span', { class: 'port-flag', title: noAr.texto }, [
                icon('alert', { size: 12 }),
                'ocupada',
              ])
            : null,
      ]),
    ]),
    el('td', {}, [
      el('a', { href: `#/projects/${encodeURIComponent(binding.project_id)}`, text: binding.project_name }),
    ]),
    el('td', {}, [
      binding.service_label,
      el('div', { class: 'field__hint mono', text: binding.service_key }),
    ]),
    el('td', { class: 'mono', text: endereco }),
    el('td', { class: 'table__end' }, [
      el(
        'button',
        {
          class: 'btn btn--sm',
          type: 'button',
          'aria-label': `Trocar a porta de ${binding.service_label} em ${binding.project_name}`,
          onClick: () => onEdit(binding),
        },
        [icon('edit', { size: 13 }), 'Trocar']
      ),
    ]),
  ]);
}

/** Linha em modo edição: o input entra no lugar da porta, na mesma linha. */
function editRow(binding, { ocupadas, escutando, onCancel, onSave }) {
  const input = el('input', {
    class: 'input input--mono port-input',
    type: 'number',
    min: String(PORTA_MIN),
    max: String(PORTA_MAX),
    value: String(binding.port),
    'aria-label': `Nova porta para ${binding.service_label}`,
  });

  // `aria-live`: o aviso aparece enquanto se digita, longe do foco. Sem isso
  // quem usa leitor de tela recebe "porta já declarada" só depois de salvar.
  const aviso = el('span', { class: 'field__hint', role: 'status', 'aria-live': 'polite' });

  const validar = () => {
    const valor = Number(input.value);
    if (!Number.isInteger(valor) || valor < PORTA_MIN || valor > PORTA_MAX) {
      aviso.textContent = `Informe um número entre ${PORTA_MIN} e ${PORTA_MAX}.`;
      aviso.style.color = 'var(--status-error)';
      return null;
    }
    if (valor !== binding.port && ocupadas.has(valor)) {
      aviso.textContent = 'Essa porta já está declarada por outro serviço.';
      aviso.style.color = 'var(--status-warning)';
      return valor;
    }
    // Escutando sem estar declarada: o painel não sabe de quem é, mas sabe que
    // está ocupada. Vale dizer antes do salvamento, não depois da falha do
    // `up`.
    if (valor !== binding.port && escutando.has(valor)) {
      const quem = escutando.get(valor)?.processo;
      aviso.textContent = `Já tem ${quem ?? 'algo'} escutando nessa porta agora.`;
      aviso.style.color = 'var(--status-warning)';
      return valor;
    }
    aviso.textContent = '';
    return valor;
  };

  input.addEventListener('input', validar);
  input.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      const valor = validar();
      if (valor !== null) onSave(binding, valor);
    }
    if (event.key === 'Escape') onCancel();
  });

  const linha = el('tr', { class: 'row--editing' }, [
    el('td', {}, [input]),
    el('td', { text: binding.project_name }),
    el('td', { text: binding.service_label }),
    el('td', {}, [
      el(
        'button',
        {
          class: 'btn btn--sm',
          type: 'button',
          title: 'Preenche com a menor porta que ninguém declarou nem está escutando.',
          onClick: () => {
            input.value = String(proximaLivre(ocupadas, escutando));
            validar();
            input.focus();
          },
        },
        ['Sugerir livre']
      ),
      aviso,
    ]),
    el('td', { class: 'table__end' }, [
      el('button', {
        class: 'btn btn--sm btn--primary',
        type: 'button',
        text: 'Salvar',
        onClick: () => {
          const valor = validar();
          if (valor !== null) onSave(binding, valor);
        },
      }),
      el('button', { class: 'btn btn--sm', type: 'button', text: 'Cancelar', onClick: onCancel }),
    ]),
  ]);

  window.setTimeout(() => {
    input.focus();
    input.select();
  }, 0);

  return linha;
}

/** Grava a nova porta reenviando a lista inteira de serviços do projeto.
 *
 * O backend não tem PATCH de serviço solto (`PUT /services` substitui tudo),
 * então buscamos o projeto para não perder `health_url` e `open_in_browser`
 * dos outros serviços no caminho — a lista da aba Services não traz esses
 * campos. */
async function gravarPorta(binding, porta) {
  const project = await api.getProject(binding.project_id);

  const items = project.services.map((service) => {
    if (service.key !== binding.service_key) return service;
    return {
      ...service,
      port: porta,
      url: comPorta(service.url, porta),
      health_url: comPorta(service.health_url, porta),
    };
  });

  await api.replaceServices(binding.project_id, items);
}

export async function renderPorts(container) {
  mount(container, skeletonGrid(3));

  let editando = null;
  //: O acordeão das portas não declaradas sobrevive ao redesenho. Sem isso a
  //: recarga automática o fechava na cara de quem estava lendo a lista.
  let acordeaoAberto = false;

  const desenhar = (mapa) => {
    const ocupadas = new Set(mapa.bindings.map((b) => b.port));

    const onEdit = (binding) => {
      editando = `${binding.project_id}:${binding.service_key}`;
      desenhar(mapa);
    };

    const onCancel = () => {
      editando = null;
      desenhar(mapa);
    };

    const onSave = async (binding, porta) => {
      if (porta !== binding.port && ocupadas.has(porta)) {
        const dono = mapa.bindings.find((b) => b.port === porta);
        const segue = window.confirm(
          `A porta ${porta} já está declarada por "${dono?.project_name}".\n\n` +
            'Salvar assim cria um conflito. Continuar?'
        );
        if (!segue) return;
      } else if (porta !== binding.port && emEscuta.has(porta)) {
        // Ocupada de fato, sem ninguém tendo declarado. O conflito não
        // apareceria em lugar nenhum do painel — só na falha do próximo `up`.
        const quem = emEscuta.get(porta)?.processo ?? 'um processo';
        const segue = window.confirm(
          `A porta ${porta} está ocupada agora por ${quem}, que nenhum ` +
            'projeto do painel declara.\n\n' +
            'O serviço não vai conseguir subir enquanto ele estiver lá. Continuar?'
        );
        if (!segue) return;
      }

      try {
        await gravarPorta(binding, porta);
      } catch (error) {
        showError(error);
        return;
      }

      toast(`${binding.service_label}: porta ${binding.port} → ${porta}.`, {
        kind: 'success',
        meta: 'Troque também no arquivo do projeto (.env, compose, vite.config).',
      });
      editando = null;
      window.dispatchEvent(new CustomEvent('devcockpit:projects-changed'));
      await carregar();
    };

    /** Adota a porta observada: a correção é sempre a mesma, então é um clique. */
    const onAdotar = async (divergencia) => {
      const binding = mapa.bindings.find(
        (b) =>
          b.project_id === divergencia.project_id &&
          b.service_key === divergencia.service_key
      );
      if (!binding) return;
      await onSave(binding, divergencia.observed_port);
    };

    /** Leva direto à edição da porta daquele serviço, na tabela abaixo. */
    const onEditarPorta = (divergencia) => {
      const binding = mapa.bindings.find(
        (b) =>
          b.project_id === divergencia.project_id &&
          b.service_key === divergencia.service_key
      );
      if (!binding) return;
      onEdit(binding);
    };

    /** Encerra um servidor largado. Confirma antes: não se desfaz. */
    const onEncerrar = async (porta, botao) => {
      const dono = porta.project_name ? ` do ${porta.project_name}` : '';
      const segue = window.confirm(
        `Encerrar o processo ${porta.process_name ?? ''} (pid ${porta.pid}) ` +
          `que está na porta ${porta.port}${dono}?\n\n` +
          `Ele roda em ${porta.cwd ?? 'origem desconhecida'}.\n` +
          'A ação não pode ser desfeita — o processo é encerrado junto com os filhos dele.'
      );
      if (!segue) return;

      botao.disabled = true;
      botao.textContent = 'Encerrando…';
      try {
        await api.stopProcess(porta.pid);
        toast(`Porta ${porta.port} liberada.`, { kind: 'success' });
        await carregar();
      } catch (error) {
        botao.disabled = false;
        botao.textContent = 'Encerrar';
        showError(error);
      }
    };

    // Quem está em cada porta, e se dá para **provar** de quem é. `forte` só
    // quando o processo roda dentro do diretório do projeto; o resto é
    // inferência pelo número declarado, que já apontou para o projeto errado.
    const emEscuta = new Map(
      (mapa.observed ?? []).map((porta) => [
        porta.port,
        {
          forte: Boolean(porta.strong_evidence),
          processo: porta.process_name,
          texto: porta.strong_evidence
            ? `${porta.process_name ?? 'processo'} de ${porta.project_name}, ` +
              `rodando em ${porta.cwd ?? 'origem desconhecida'}.`
            : `Ocupada por ${porta.process_name ?? 'processo desconhecido'}. ` +
              'O painel não consegue provar que é deste projeto — pode ser ' +
              'container de outro, ou algo fora dele.',
        },
      ])
    );

    const linhas = mapa.bindings.map((binding) =>
      editando === `${binding.project_id}:${binding.service_key}`
        ? editRow(binding, { ocupadas, escutando: emEscuta, onCancel, onSave })
        : bindingRow(binding, { onEdit, noAr: emEscuta.get(binding.port) ?? null })
    );

    const header = pageHeader({
      title: 'Ports',
      subtitle: [
        `${mapa.items.length} porta(s) declarada(s)`,
        `${mapa.conflicts} conflito(s)`,
        // Só aparece quando há o que dizer: um "0 divergências" fixo vira
        // ruído e a pessoa para de ler a linha inteira.
        mapa.mismatches?.length ? `${mapa.mismatches.length} em outra porta` : null,
      ]
        .filter(Boolean)
        .join(' · '),
      actions: [
        el(
          'button',
          { class: 'btn', type: 'button', onClick: () => carregar() },
          [icon('refresh', { size: 15 }), 'Recarregar']
        ),
        el(
          'button',
          { class: 'btn', type: 'button', onClick: () => navigate('/projects') },
          ['Projects']
        ),
      ],
    });

    if (!mapa.bindings.length) {
      mount(
        container,
        header,
        emptyState({
          iconName: 'plug',
          title: 'Nenhuma porta declarada',
          text:
            'A detecção preenche as portas a partir do Compose e do Vite. ' +
            'Rode a detecção num projeto, ou cadastre o serviço na aba Services.',
          actions: [
            el('button', {
              class: 'btn btn--primary',
              text: 'Ir para Projects',
              onClick: () => navigate('/projects'),
            }),
          ],
        })
      );
      return;
    }

    mount(
      container,
      header,
      // A divergência vem antes do conflito: o conflito é entre dois números
      // que alguém escolheu, a divergência é entre o que se escolheu e o que a
      // máquina está fazendo — e é a que faz o painel parecer quebrado.
      // Antes do resto: é a única coisa nesta tela que está custando uma porta
      // agora, e a única com um processo de pé do outro lado.
      orphanSection(mapa, { onEncerrar }),
      unmanagedSection(mapa, { onEncerrar }),
      mismatchAlert(mapa, { onAdotar, onEditarPorta }),
      conflictAlert(mapa),
      el('p', {
        class: 'field__hint',
        style: 'margin-bottom:var(--sp-3)',
        text:
          'Trocar aqui muda o que o DevCockpit verifica e abre. O servidor do ' +
          'projeto continua na porta do arquivo dele até você trocar lá também.',
      }),
      el('div', { class: 'table-wrap' }, [
        el('table', { class: 'table table--ports' }, [
          el('thead', {}, [
            el('tr', {}, [
              el('th', { text: 'Porta' }),
              el('th', { text: 'Projeto' }),
              el('th', { text: 'Serviço' }),
              el('th', { text: 'Endereço' }),
              // A coluna de ação precisa de nome: um `th` vazio deixa o leitor
              // de tela anunciar "coluna 5, em branco" no lugar de "Ações".
              el('th', { class: 'table__end' }, [
                el('span', { class: 'visually-hidden', text: 'Ações' }),
              ]),
            ]),
          ]),
          el('tbody', {}, linhas),
        ]),
      ]),
      unclaimedSection(mapa, {
        aberto: acordeaoAberto,
        onToggle: (estado) => {
          acordeaoAberto = estado;
        },
      })
    );
  };

  const carregar = async () => {
    try {
      desenhar(await api.ports());
    } catch (error) {
      mount(container, el('p', { class: 'loading', text: error.message }));
    }
  };

  await carregar();

  // A recarga automática se cala em três situações, e as três importam:
  //
  // - **edição aberta**: redesenhar apaga o input com o número já digitado;
  // - **aba escondida**: dado fresco que ninguém está olhando só gasta;
  // - **tela trocada**: o timer morre junto com a rota.
  //
  // A terceira já foi um bug: o teste era `container.isConnected`, e o
  // container é o `<main id="view">`, que **nunca** sai do DOM — só o conteúdo
  // dele é trocado. O timer sobrevivia à navegação e, a cada seis segundos,
  // redesenhava esta tela por cima da que estivesse aberta. Quem sabe que a
  // rota mudou é o roteador, e é ele quem manda parar.
  const timer = window.setInterval(() => {
    if (editando !== null || document.visibilityState !== 'visible') return;
    void carregar();
  }, RECARGA_MS);

  aoSairDaRota(() => window.clearInterval(timer));
}
