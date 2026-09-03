// Conjunto de ícones desenhado, não emprestado da fonte do sistema.
//
// Antes a UI usava caracteres Unicode (★, ◌, ⎈) no lugar de ícone. Eles mudam
// de forma, de peso e de alinhamento conforme a fonte instalada, não obedecem
// `currentColor` de maneira previsível e não têm como ser alinhados ao texto —
// ou seja, não são controláveis por design token nenhum.
//
// Todos aqui compartilham o mesmo desenho: grade de 24, traço de 1.75,
// extremidades e junções arredondadas. Um traço só, uma linguagem só.

const NS = 'http://www.w3.org/2000/svg';

/** Cada valor é a lista de sub-elementos: [tag, atributos]. */
const PATHS = {
  pin: [
    ['path', { d: 'M12 17v5' }],
    ['path', { d: 'M9 10.8V4h6v6.8l2.6 3.5a1 1 0 0 1-.8 1.6H7.2a1 1 0 0 1-.8-1.6L9 10.8Z' }],
  ],
  code: [
    ['path', { d: 'm9 8-4 4 4 4' }],
    ['path', { d: 'm15 8 4 4-4 4' }],
  ],
  folder: [
    ['path', { d: 'M4 7a2 2 0 0 1 2-2h3l2 2.5h7a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7Z' }],
  ],
  terminal: [
    ['path', { d: 'm5 8 4 4-4 4' }],
    ['path', { d: 'M12 17h7' }],
  ],
  container: [
    ['path', { d: 'M12 3.5 20 8v8l-8 4.5L4 16V8l8-4.5Z' }],
    ['path', { d: 'M4 8l8 4.5L20 8' }],
    ['path', { d: 'M12 12.5V20.5' }],
  ],
  branch: [
    ['circle', { cx: '7', cy: '6', r: '2.2' }],
    ['circle', { cx: '7', cy: '18', r: '2.2' }],
    ['circle', { cx: '17', cy: '9', r: '2.2' }],
    ['path', { d: 'M7 8.2v7.6' }],
    ['path', { d: 'M17 11.2c0 3-2.8 4.2-5.6 4.6' }],
  ],
  pulse: [
    ['path', { d: 'M3 12h4l2.5-6 5 12L17 12h4' }],
  ],
  search: [
    ['circle', { cx: '11', cy: '11', r: '6' }],
    ['path', { d: 'm20 20-4.5-4.5' }],
  ],
  trash: [
    ['path', { d: 'M4 7h16' }],
    ['path', { d: 'M10 7V5h4v2' }],
    ['path', { d: 'M6 7v12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V7' }],
  ],
  plus: [
    ['path', { d: 'M12 5v14' }],
    ['path', { d: 'M5 12h14' }],
  ],
  scan: [
    ['path', { d: 'M4 8V6a2 2 0 0 1 2-2h2' }],
    ['path', { d: 'M16 4h2a2 2 0 0 1 2 2v2' }],
    ['path', { d: 'M20 16v2a2 2 0 0 1-2 2h-2' }],
    ['path', { d: 'M8 20H6a2 2 0 0 1-2-2v-2' }],
    ['path', { d: 'M4 12h16' }],
  ],
  refresh: [
    ['path', { d: 'M20 11a8 8 0 0 0-13.7-5.2L4 8' }],
    ['path', { d: 'M4 5v3h3' }],
    ['path', { d: 'M4 13a8 8 0 0 0 13.7 5.2L20 16' }],
    ['path', { d: 'M20 19v-3h-3' }],
  ],
  external: [
    ['path', { d: 'M13 5h6v6' }],
    ['path', { d: 'M19 5 11 13' }],
    ['path', { d: 'M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4' }],
  ],
  chevron: [['path', { d: 'm9 5 7 7-7 7' }]],
  check: [['path', { d: 'm5 12.5 4.5 4.5L19 7.5' }]],
  dot: [['circle', { cx: '12', cy: '12', r: '4', fill: 'currentColor', stroke: 'none' }]],
  close: [
    ['path', { d: 'M6 6 18 18' }],
    ['path', { d: 'M18 6 6 18' }],
  ],
  alert: [
    ['path', { d: 'M12 4.5 21 19H3l9-14.5Z' }],
    ['path', { d: 'M12 10v4' }],
    ['path', { d: 'M12 17h.01' }],
  ],
  grid: [
    ['rect', { x: '4', y: '4', width: '7', height: '7', rx: '1.5' }],
    ['rect', { x: '13', y: '4', width: '7', height: '7', rx: '1.5' }],
    ['rect', { x: '4', y: '13', width: '7', height: '7', rx: '1.5' }],
    ['rect', { x: '13', y: '13', width: '7', height: '7', rx: '1.5' }],
  ],
  layers: [
    ['path', { d: 'm12 3.5 8 4.2-8 4.3-8-4.3 8-4.2Z' }],
    ['path', { d: 'm4 12.5 8 4.3 8-4.3' }],
    ['path', { d: 'm4 16.8 8 4.2 8-4.2' }],
  ],
  gear: [
    ['circle', { cx: '12', cy: '12', r: '3' }],
    ['path', { d: 'M12 3.2v2.2M12 18.6v2.2M20.8 12h-2.2M5.4 12H3.2M18.2 5.8l-1.6 1.6M7.4 16.6l-1.6 1.6M18.2 18.2l-1.6-1.6M7.4 7.4 5.8 5.8' }],
  ],
  gauge: [
    ['path', { d: 'M4.5 16a7.5 7.5 0 1 1 15 0' }],
    ['path', { d: 'M12 16 15.2 10' }],
    ['path', { d: 'M12 16h.01' }],
  ],
  power: [
    ['path', { d: 'M12 4v7' }],
    ['path', { d: 'M7.5 7.2a7 7 0 1 0 9 0' }],
  ],
  sidebar: [
    ['rect', { x: '3.5', y: '4.5', width: '17', height: '15', rx: '2' }],
    ['path', { d: 'M10 4.5v15' }],
  ],
  plug: [
    ['path', { d: 'M9 3v5' }],
    ['path', { d: 'M15 3v5' }],
    ['path', { d: 'M6.5 8h11v2.5a5.5 5.5 0 0 1-11 0V8Z' }],
    ['path', { d: 'M12 16v5' }],
  ],
  edit: [
    ['path', { d: 'M4 20h4L19 9a2.1 2.1 0 0 0-3-3L5 17v3Z' }],
    ['path', { d: 'm14.5 7.5 2 2' }],
  ],
  inbox: [
    ['path', { d: 'M4 13h4l1.5 3h5L16 13h4' }],
    ['path', { d: 'M5.5 5h13l1.5 8v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-4l1.5-8Z' }],
  ],
  // Núcleo com três satélites: o desenho do HyperBrain reduzido a 24px.
  graph: [
    ['path', { d: 'm10.4 10.4-3.6-3.6M13.6 10.4l3.6-3.6M12 14.6V19' }],
    ['circle', { cx: '12', cy: '12', r: '2.6' }],
    ['circle', { cx: '5.5', cy: '5.5', r: '1.9' }],
    ['circle', { cx: '18.5', cy: '5.5', r: '1.9' }],
    ['circle', { cx: '12', cy: '20', r: '1.9' }],
  ],
};

/**
 * Ícone como elemento SVG.
 *
 * Decorativo por padrão (`aria-hidden`): o texto ao lado já diz o que é. Passe
 * `label` só quando o ícone estiver sozinho e precisar ser anunciado.
 */
export function icon(name, { size = 16, label = null, className = '' } = {}) {
  const shapes = PATHS[name];
  if (!shapes) throw new Error(`Ícone desconhecido: ${name}`);

  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('width', String(size));
  svg.setAttribute('height', String(size));
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '1.75');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  svg.setAttribute('class', `icon${className ? ` ${className}` : ''}`);

  if (label) {
    svg.setAttribute('role', 'img');
    const title = document.createElementNS(NS, 'title');
    title.textContent = label;
    svg.append(title);
  } else {
    svg.setAttribute('aria-hidden', 'true');
  }

  for (const [tag, attrs] of shapes) {
    const shape = document.createElementNS(NS, tag);
    for (const [key, value] of Object.entries(attrs)) shape.setAttribute(key, value);
    svg.append(shape);
  }

  return svg;
}

export const ICON_NAMES = Object.keys(PATHS);
