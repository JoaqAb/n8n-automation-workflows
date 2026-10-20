// Captura los tramos del lienzo de n8n con la regla medida sobre los pixeles:
// la etiqueta de un nodo mide 16 px de cuerpo en el lienzo, siempre. Para que aterrice en los
// 26 px de piso de la lamina, el recorte no puede abarcar mas de 881 px de lienzo. Eso son
// tres nodos: la separacion es de 220 px y las etiquetas sobresalen del cuadro del nodo.
// El motor verifica cada tramo antes de guardarlo y falla si no llega al piso.
//
//   node tramos.mjs <archivo-de-tramos.json> <carpeta de salida>
import { chromium } from 'playwright';
import { readFileSync, mkdirSync, writeFileSync, existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const [lista, destino, altoArg] = process.argv.slice(2);
const ALTO = Number(altoArg || 1000);
// Cuanto puede asomar un vecino adentro del recorte sin que se lea como un
// pedazo cortado. Seis pixeles de pantalla: menos que un trazo de letra.
const ASOMO = Number(process.env.ASOMO ?? 6);
const tramos = JSON.parse(readFileSync(lista, 'utf8'));
mkdirSync(destino, { recursive: true });
// El login de n8n sale de local/.n8n-cred, que esta gitignoreado:
//
//   email: vos@ejemplo.test
//   pass: loquesea
//
// Antes esto leia un archivo en el scratchpad de una sesion, que se borro y
// dejo el script sin poder entrar. Las variables de entorno N8N_EMAIL y
// N8N_PASS pisan el archivo si estan puestas.
const credEnv = process.env.N8N_EMAIL && process.env.N8N_PASS;
const rutaCred = path.join(path.dirname(fileURLToPath(import.meta.url)), '.n8n-cred');
if (!credEnv && !existsSync(rutaCred)) {
  console.error(`falta ${rutaCred} (o las variables N8N_EMAIL y N8N_PASS).\n` +
                'Son dos lineas: "email: ..." y "pass: ...".');
  process.exit(1);
}
const txt = credEnv ? '' : readFileSync(rutaCred, 'utf8');
const email = process.env.N8N_EMAIL ?? txt.match(/email:\s*(\S+)/)[1];
const pass = process.env.N8N_PASS ?? txt.match(/pass:\s*(\S+)/)[1];

const b = await chromium.launch({ headless: true });
const p = await (await b.newContext({ viewport: { width: 1600, height: ALTO }, deviceScaleFactor: 2 })).newPage();
await p.goto('http://localhost:5678/signin', { waitUntil: 'domcontentloaded' });
await p.waitForTimeout(2000);
if (await p.locator('input[type=email]').count()) {
  await p.locator('input[type=email]').first().fill(email);
  await p.locator('input[type=password]').first().fill(pass);
  await p.keyboard.press('Enter');
  await p.waitForTimeout(5000);
}

// caja que encierra a los nodos pedidos, con sus etiquetas
const caja = (nombres) => p.evaluate((ns) => {
  const todos = [...document.querySelectorAll('[data-test-id="canvas-node"]')];
  const elegidos = ns.map((n) => todos.find((e) => e.getAttribute('data-node-name') === n)).filter(Boolean);
  if (elegidos.length !== ns.length) return null;
  const lienzo = document.querySelector('.vue-flow') || document.body;
  const hojas = [...lienzo.querySelectorAll('*')].filter(
    (e) => e.children.length === 0 && e.textContent.trim() && e.getBoundingClientRect().width > 0);

  const mio = (e) => elegidos.some((n) => n === e || n.contains(e));
  let x = 1e9, y = 1e9, x2 = -1e9, y2 = -1e9, etiqueta = 0;
  for (const el of elegidos) {
    for (const r of [el.getBoundingClientRect(), ...[...el.querySelectorAll('*')].map((h) => h.getBoundingClientRect())]) {
      if (!r.width) continue;
      x = Math.min(x, r.x); y = Math.min(y, r.y); x2 = Math.max(x2, r.right); y2 = Math.max(y2, r.bottom);
    }
    const nombre = el.getAttribute('data-node-name');
    for (const h of el.querySelectorAll('*')) {
      if (h.children.length === 0 && h.textContent.trim() === nombre) {
        etiqueta = Math.max(etiqueta, parseFloat(getComputedStyle(h).fontSize));
      }
    }
  }
  // Todo lo que no es del tramo: los otros nodos enteros y cualquier texto suelto del lienzo,
  // incluidos los "1 item" de las flechas y los true/false de las bifurcaciones.
  const ajenos = [];
  const anotar = (r) => { if (r.width > 0 && r.height > 0) ajenos.push({ x: r.x, y: r.y, x2: r.right, y2: r.bottom }); };
  for (const el of todos) {
    if (elegidos.includes(el)) continue;
    anotar(el.getBoundingClientRect());
    for (const h of el.querySelectorAll('*')) if (h.children.length === 0 && h.textContent.trim()) anotar(h.getBoundingClientRect());
  }
  for (const h of hojas) if (!mio(h) && !todos.some((n) => n.contains(h))) anotar(h.getBoundingClientRect());

  const xs = todos.map((e) => e.getBoundingClientRect().x).sort((a, b) => a - b);
  let sep = 0;
  for (let i = 1; i < xs.length; i++) { const d = xs[i] - xs[i - 1]; if (d > 5 && (!sep || d < sep)) sep = d; }
  const escala = sep ? sep / 220 : 1;
  return { x, y, x2, y2, etiqueta, escala, ajenos };
}, nombres);

const registro = [];
const fallas = [];
let urlActual = '';
for (const t of tramos) {
  if (t.url !== urlActual) {
    await p.goto(t.url, { waitUntil: 'domcontentloaded' });
    await p.waitForTimeout(7000);
    await p.keyboard.press('Escape');
    await p.mouse.click(1450, ALTO - 60);
    // El cromo de la herramienta no entra en ningun recorte. En la vista de
    // ejecucion la lista de corridas llega a tocar el primer nodo, asi que se
    // esconde antes de medir: esconder el cromo no es tocar el lienzo.
    await p.addStyleTag({ content: `[data-test-id="executions-sidebar"] { display: none !important; }` });
    await p.waitForTimeout(900);
    urlActual = t.url;
  }
  await p.keyboard.press('1');
  await p.waitForTimeout(1200);
  // El zoom no se fija de antemano: se sube hasta que el tramo mide lo que tiene que medir.
  // La captura nunca puede salir mas angosta que los 1432 px de lamina, o se amplia y se ve
  // blanda. Objetivo: entre 800 y 1400 px de pantalla, que a dos por pixel son 1600 a 2800.
  let c = await caja(t.nodos);
  for (let i = 0; i < 10 && c; i++) {
    const ancho = c.x2 - c.x;
    if (ancho >= 760 && ancho <= 1300) break;
    await p.keyboard.press(ancho < 800 ? '=' : '-');
    await p.waitForTimeout(450);
    c = await caja(t.nodos);
  }
  let clip = null, partidos = 0, asomos = [];
  for (let intento = 0; intento < 4 && !clip; intento++) {
  if (intento) { await p.keyboard.press('-'); await p.waitForTimeout(500); c = await caja(t.nodos); }
  for (let i = 0; i < 9 && c; i++) {
    const dx = (c.x + c.x2) / 2 - 800, dy = (c.y + c.y2) / 2 - ALTO / 2;
    if (Math.abs(dx) < 40 && Math.abs(dy) < 40) break;
    await p.mouse.move(1450, ALTO - 60);
    if (Math.abs(dx) >= 40) { const k = Math.min(16, Math.abs(Math.round(dx / 200))); for (let j = 0; j < k; j++) { await p.mouse.wheel(dx > 0 ? 200 : -200, 0); await p.waitForTimeout(90); } }
    if (Math.abs(dy) >= 40) { const k = Math.min(16, Math.abs(Math.round(dy / 150))); for (let j = 0; j < k; j++) { await p.mouse.wheel(0, dy > 0 ? 150 : -150); await p.waitForTimeout(90); } }
    await p.waitForTimeout(300);
    c = await caja(t.nodos);
  }
  await p.mouse.move(1570, 25);
  await p.waitForTimeout(900);
  c = await caja(t.nodos);
  if (!c) break;
  const m = t.margen ?? 22;
  // Un vecino entero adentro del recorte no molesta: lo que delata un recorte es un pedazo
  // de algo cortado. Asi que primero se intenta dejarlo afuera, y si no se puede, se agranda
  // el recorte hasta que entre entero. Despues el piso de 26 px decide si el tramo sirve.
  let x1 = c.x - m, y1 = c.y - m, x2 = c.x2 + m, y2 = c.y2 + m;
  for (let vuelta = 0; vuelta < 6; vuelta++) {
    let tocado = false;
    for (const a of c.ajenos) {
      const cruza = !(a.x2 <= x1 || a.x >= x2 || a.y2 <= y1 || a.y >= y2);
      if (!cruza) continue;
      const entero = a.x >= x1 && a.x2 <= x2 && a.y >= y1 && a.y2 <= y2;
      if (entero) continue;
      tocado = true;
      if (a.y2 <= c.y) y1 = Math.max(y1, a.y2 + 2);          // esta arriba del tramo
      else if (a.y >= c.y2) y2 = Math.min(y2, a.y - 2);       // esta abajo
      else if (a.x2 <= c.x) x1 = Math.max(x1, a.x2 + 2);      // esta a la izquierda
      else if (a.x >= c.x2) x2 = Math.min(x2, a.x - 2);       // esta a la derecha
      else {                                                  // se superpone: entra entero
        x1 = Math.min(x1, a.x - 6); x2 = Math.max(x2, a.x2 + 6);
        y1 = Math.min(y1, a.y - 6); y2 = Math.max(y2, a.y2 + 6);
      }
    }
    if (!tocado) break;
  }
  const tentativa = {
    x: Math.max(0, Math.round(x1)), y: Math.max(0, Math.round(y1)),
    width: Math.round(x2 - x1), height: Math.round(y2 - y1),
  };
  const entra = tentativa.x <= c.x && tentativa.y <= c.y
    && tentativa.x + tentativa.width >= c.x2 && tentativa.y + tentativa.height >= c.y2
    && tentativa.x + tentativa.width <= 1600 && tentativa.y + tentativa.height <= ALTO;
  // Las seis vueltas de arriba son el intento, no la garantia: si no convergen,
  // antes la captura se guardaba igual. Asi salieron los tramos del caso 06 con
  // una "n" suelta a la izquierda y un "Res" cortado a la derecha. Ademas el
  // Math.max(0, ...) puede traer el borde a 0 y partir un vecino que asoma
  // desde fuera de la pantalla. Aca se verifica el recorte final: un vecino
  // entero adentro no molesta, uno partido por el borde si.
  // Lo que delata un recorte no es que roce un vecino, es que deje adentro un
  // PEDAZO RECONOCIBLE de el. Asi que no se cuenta si cruza, se mide cuanto
  // asoma: la interseccion del vecino con el recorte. Si su lado mas corto no
  // llega a ASOMO px, es un roce de antialias o de sombra y no se ve. Si lo
  // pasa, ahi hay media etiqueta o medio nodo, que es lo que salio en el caso
  // 06 como una "n" suelta a la izquierda y un "Res" cortado a la derecha.
  asomos = entra ? c.ajenos.map((a) => {
    const bx1 = tentativa.x, by1 = tentativa.y;
    const bx2 = bx1 + tentativa.width, by2 = by1 + tentativa.height;
    const entero = a.x >= bx1 && a.x2 <= bx2 && a.y >= by1 && a.y2 <= by2;
    if (entero) return null;
    const ancho = Math.min(a.x2, bx2) - Math.max(a.x, bx1);
    const alto = Math.min(a.y2, by2) - Math.max(a.y, by1);
    if (ancho <= 0 || alto <= 0) return null;             // no cruza
    return { ancho: Math.round(ancho), alto: Math.round(alto),
             lado: a.x < bx1 ? 'izq' : a.x2 > bx2 ? 'der' : a.y < by1 ? 'arriba' : 'abajo' };
  }).filter((v) => v && Math.min(v.ancho, v.alto) > ASOMO) : [];
  partidos = asomos.length;
  if (entra && !partidos) clip = tentativa;
  }
  if (!clip) {
    const detalle = asomos.map((a) => `${a.lado} ${a.ancho}x${a.alto}`).join(', ');
    const motivo = partidos ? `${partidos} vecinos partidos: ${detalle}` : 'no entra en la pantalla sin cortar un vecino';
    console.log(`FALLA  ${t.nombre}  ${motivo}`);
    fallas.push({ nombre: t.nombre, motivo });
    continue;
  }
  // El cuerpo de la etiqueta en la lamina: 16 px de hoja de estilo, por la escala del lienzo,
  // por lo que se achica o se agranda al entrar en los 1432 px del area util.
  const cuerpo = c.etiqueta * c.escala * 1432 / clip.width;
  if (cuerpo < 26) {
    console.log(`FALLA  ${t.nombre}  el cuerpo aterriza en ${cuerpo.toFixed(1)} px, abajo del piso de 26`);
    fallas.push({ nombre: t.nombre, cuerpo: Math.round(cuerpo * 10) / 10 });
    continue;
  }
  const archivo = path.join(destino, t.nombre + '.png');
  await p.screenshot({ path: archivo, clip });
  registro.push({ nombre: t.nombre, nodos: t.nodos.length, clip, escala: c.escala,
                  lienzoEnElRecorte: Math.round(clip.width / c.escala),
                  cuerpoEnLamina: Math.round(cuerpo * 10) / 10 });
  console.log(`${t.nombre}  ${t.nodos.length} nodos  captura ${clip.width * 2}x${clip.height * 2}  cuerpo en lamina ${cuerpo.toFixed(1)} px`);
}
writeFileSync(path.join(destino, 'medidas.json'), JSON.stringify({ tramos: registro, fallas }, null, 1));
console.log(`\n${registro.length} tramos guardados, ${fallas.length} abajo del piso`);
await b.close();
