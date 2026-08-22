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
import { navigate } from '../router.js';

const PORTA_MIN = 1;
const PORTA_MAX = 65535;
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

function proximaLivre(ocupadas, apartir = SUGESTAO_INICIO) {
  let porta = apartir;
  while (porta < PORTA_MAX && ocupadas.has(porta)) porta += 1;
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

/** Linha em modo leitura. */
function bindingRow(binding, { onEdit }) {
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
function editRow(binding, { ocupadas, onCancel, onSave }) {
  const input = el('input', {
    class: 'input input--mono port-input',
    type: 'number',
    min: String(PORTA_MIN),
    max: String(PORTA_MAX),
    value: String(binding.port),
    'aria-label': `Nova porta para ${binding.service_label}`,
  });

  const aviso = el('span', { class: 'field__hint' });

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
          title: 'Preenche com a menor porta que ninguém declarou.',
          onClick: () => {
            input.value = String(proximaLivre(ocupadas));
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

    const linhas = mapa.bindings.map((binding) =>
      editando === `${binding.project_id}:${binding.service_key}`
        ? editRow(binding, { ocupadas, onCancel, onSave })
        : bindingRow(binding, { onEdit })
    );

    const header = pageHeader({
      title: 'Ports',
      subtitle: `${mapa.items.length} porta(s) declarada(s) · ${mapa.conflicts} conflito(s)`,
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
              el('th', { class: 'table__end', text: '' }),
            ]),
          ]),
          el('tbody', {}, linhas),
        ]),
      ])
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
}
