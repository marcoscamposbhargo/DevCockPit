// Painel da máquina: como ela está, e qual projeto está custando.
//
// A segunda metade é o que só este painel sabe responder. O Gerenciador de
// Tarefas mostra dezoito `node.exe` sem dono; aqui cada árvore de processo tem
// projeto, porque foi o painel que a subiu.
//
// O histórico é guardado **no cliente**, numa janela curta em memória. Não vai
// para o banco de propósito: é o "e antes?" dos últimos minutos, e nada disso
// tem valor amanhã. Persistir seria criar uma tabela que só cresce para
// responder pergunta que ninguém faz no dia seguinte.

import { api } from './api.js';
import { bar, gauge, sparkline, tomPara } from './charts.js';
import { el, mount } from './dom.js';
import { icon } from './icons.js';

const INTERVALO_MS = 3000;
//: Sessenta amostras a cada três segundos são três minutos de história — o
//: bastante para ver uma subida se formar, e pouco o bastante para caber na
//: memória sem ninguém pensar no assunto.
const JANELA = 60;

const historico = { cpu: [], memoria: [] };

function empurrar(serie, valor) {
  serie.push(valor);
  if (serie.length > JANELA) serie.shift();
}

function linhaServidor(servidor) {
  const tom = tomPara(servidor.cpu_percent, { atencao: 40, critico: 70 });

  return el('tr', {}, [
    el('td', {}, [
      el('a', {
        href: `#/projects/${encodeURIComponent(servidor.project_id)}?tab=server`,
        text: servidor.project_name,
      }),
    ]),
    el('td', { class: 'machine__barra' }, [
      bar(servidor.cpu_percent / 100, {
        tom,
        titulo: `${servidor.cpu_percent}% da máquina`,
      }),
      el('span', { class: 'field__hint mono', text: `${servidor.cpu_percent}%` }),
    ]),
    el('td', {
      class: 'mono field__hint',
      text: `${servidor.memory_mb >= 1024
        ? `${(servidor.memory_mb / 1024).toFixed(1)} GB`
        : `${Math.round(servidor.memory_mb)} MB`}`,
    }),
    el('td', {
      class: 'field__hint',
      // A contagem explica por que o número de CPU não é o do processo pai:
      // `npm run dev` é um `cmd.exe` que gasta zero e um `node` que gasta tudo.
      text: `${servidor.process_count} proc.`,
      title: 'Processos na árvore deste servidor, somados na medição.',
    }),
  ]);
}

function conteudo(dados) {
  const m = dados.machine;

  const medidores = el('div', { class: 'machine__gauges' }, [
    gauge(m.cpu_percent, {
      rotulo: 'Processador',
      detalhe: `${m.cpu_count} núcleos`,
      tom: tomPara(m.cpu_percent),
    }),
    gauge(m.memory_percent, {
      rotulo: 'Memória',
      detalhe: `${m.memory_used_gb} de ${m.memory_total_gb} GB`,
      tom: tomPara(m.memory_percent),
    }),
    gauge(m.disk_percent, {
      rotulo: 'Disco',
      detalhe: `${m.disk_free_gb} GB livres`,
      tom: tomPara(m.disk_percent, { atencao: 85, critico: 95 }),
    }),
    // Temperatura não é percentual: o arco usaria uma escala inventada. Um
    // número com a unidade é honesto, e o rótulo diz que zona é essa — a ACPI
    // marca bem menos que o núcleo do processador, e chamá-la de "CPU" seria
    // mentira.
    el('div', { class: 'gauge-wrap gauge-wrap--texto' }, [
      el('div', {
        class: 'gauge__valor gauge__valor--grande',
        text: m.temperature_c === null ? '—' : `${m.temperature_c}°`,
      }),
      el('div', { class: 'gauge__rotulo', text: 'Zona térmica' }),
      el('div', {
        class: 'gauge__detalhe',
        text: m.temperature_c === null ? 'não exposta' : 'sensor ACPI da placa',
        title:
          m.temperature_c === null
            ? 'Esta máquina não expõe zona térmica ao Windows. Comum em desktop e em máquina virtual.'
            : 'Sensor da placa, não do núcleo do processador — marca bem menos que um HWMonitor.',
      }),
    ]),
  ]);

  const linhas = el('div', { class: 'machine__series' }, [
    el('div', { class: 'machine__serie' }, [
      el('span', { class: 'field__hint', text: 'Processador, últimos 3 min' }),
      sparkline(historico.cpu, { rotulo: 'Uso do processador nos últimos minutos' }),
    ]),
    el('div', { class: 'machine__serie' }, [
      el('span', { class: 'field__hint', text: 'Memória, últimos 3 min' }),
      sparkline(historico.memoria, { rotulo: 'Uso de memória nos últimos minutos' }),
    ]),
  ]);

  const servidores = dados.servers.length
    ? el('div', { class: 'table-wrap' }, [
        el('table', { class: 'table' }, [
          el('thead', {}, [
            el('tr', {}, [
              el('th', { text: 'Servidor' }),
              el('th', { text: 'Processador' }),
              el('th', { text: 'Memória' }),
              el('th', { text: '' }),
            ]),
          ]),
          el('tbody', {}, dados.servers.map(linhaServidor)),
        ]),
      ])
    : el('p', {
        class: 'panel__empty',
        text: 'Nenhum servidor iniciado pelo painel. Ligue um projeto para ver o custo dele aqui.',
      });

  return [medidores, linhas, el('div', { class: 'machine__servidores' }, [servidores])];
}

/** Monta o painel e mantém ele vivo. Devolve `parar` para a tela desmontar. */
export function machinePanel() {
  const corpo = el('div', { class: 'machine' }, [
    el('p', { class: 'panel__empty', text: 'Lendo o estado da máquina…' }),
  ]);

  let timer = 0;
  let parado = false;
  let jaMontou = false;

  const pararTudo = () => {
    parado = true;
    if (timer) {
      window.clearInterval(timer);
      timer = 0;
    }
  };

  const atualizar = async () => {
    if (parado) return;

    // O roteador troca a tela sem avisar quem estava nela: sair do dashboard
    // deixava este relógio batendo para sempre, consultando a máquina a cada
    // três segundos para desenhar num container que já saiu do DOM. Perguntar
    // ao próprio elemento se ele ainda está na página resolve sem exigir um
    // gancho de desmontagem no roteador.
    //
    // `jaMontou` existe porque a primeira leitura acontece **antes** de o
    // elemento entrar no DOM — quem chama monta a tela depois de pedir o
    // painel. Sem essa ressalva o painel se desligava na partida, e a tela
    // ficava para sempre no "Lendo o estado da máquina…".
    if (corpo.isConnected) jaMontou = true;
    else if (jaMontou) {
      pararTudo();
      return;
    }

    // A aba escondida não precisa de dado fresco, e o relógio só gastaria
    // bateria: a leitura volta quando a aba volta.
    if (document.visibilityState !== 'visible') return;

    try {
      const dados = await api.systemMetrics();
      empurrar(historico.cpu, dados.machine.cpu_percent);
      empurrar(historico.memoria, dados.machine.memory_percent);
      mount(corpo, ...conteudo(dados));
    } catch {
      mount(
        corpo,
        el('p', { class: 'panel__empty' }, [
          icon('alert', { size: 14 }),
          ' Não foi possível ler o estado da máquina.',
        ])
      );
    }
  };

  atualizar();
  timer = window.setInterval(atualizar, INTERVALO_MS);

  return { element: corpo, parar: pararTudo };
}
