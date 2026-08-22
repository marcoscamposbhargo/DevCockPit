// Criação de elementos por função.
//
// Regra rígida (docs/11-ui-ux-spec.md): `innerHTML` nunca recebe dado vindo da
// API. Nome de branch, mensagem de commit, path e log de container são
// conteúdo não confiável, e esta página tem acesso à API que executa comandos.

export function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);

  for (const [key, value] of Object.entries(props)) {
    if (value === null || value === undefined || value === false) continue;

    if (key === 'class') {
      node.className = value;
    } else if (key === 'dataset') {
      for (const [dataKey, dataValue] of Object.entries(value)) {
        if (dataValue !== null && dataValue !== undefined) {
          node.dataset[dataKey] = String(dataValue);
        }
      }
    } else if (key.startsWith('on') && typeof value === 'function') {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (key === 'text') {
      node.textContent = String(value);
    } else {
      node.setAttribute(key, value === true ? '' : String(value));
    }
  }

  for (const child of [].concat(children)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }

  return node;
}

export function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

export function mount(container, ...nodes) {
  clear(container);
  container.append(...nodes.filter(Boolean));
}
