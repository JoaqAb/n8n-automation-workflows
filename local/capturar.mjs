// Captura del lienzo de n8n centrada en un nodo, con el cromo fuera del recorte.
//   node capturar.mjs <url> <nodo a centrar> <salida.png> [zoom] [ancho] [alto]
import { chromium } from 'playwright';
import { readFileSync } from 'node:fs';

const [url, objetivo, salida, zoom = '6', ancho = '1300', alto = '620', x0 = '160', y0 = '120'] = process.argv.slice(2);
const txt = readFileSync('/tmp/claude-1000/-home-joaquin-proyectos/93f977d9-f8dc-41c2-967b-ba835c581639/scratchpad/n8n-local.txt', 'utf8');
const email = txt.match(/email:\s*(\S+)/)[1], pass = txt.match(/pass:\s*(\S+)/)[1];

const b = await chromium.launch({ headless: true });
const p = await (await b.newContext({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 2 })).newPage();
await p.goto('http://localhost:5678/signin', { waitUntil: 'domcontentloaded' });
await p.waitForTimeout(2000);
if (await p.locator('input[type=email]').count()) {
  await p.locator('input[type=email]').first().fill(email);
  await p.locator('input[type=password]').first().fill(pass);
  await p.keyboard.press('Enter');
  await p.waitForTimeout(5000);
}
await p.goto(url, { waitUntil: 'domcontentloaded' });
await p.waitForTimeout(7000);
await p.keyboard.press('Escape');
await p.mouse.click(1450, 940);          // cerrar paneles sin tocar ningun nodo
await p.waitForTimeout(700);
await p.keyboard.press('1');
await p.waitForTimeout(1500);
for (let i = 0; i < Number(zoom); i++) { await p.keyboard.press('='); await p.waitForTimeout(600); }
await p.waitForTimeout(1000);

const pos = async (nombre) => p.evaluate((n) => {
  const el = [...document.querySelectorAll('[data-test-id="canvas-node"]')]
    .find((e) => (e.getAttribute('data-node-name') || e.innerText).includes(n));
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };
}, nombre);

const centroX = Number(x0) + Number(ancho) / 4, centroY = Number(y0) + Number(alto) / 2;
for (let paso = 0; paso < 7; paso++) {
  const q = await pos(objetivo);
  if (!q) break;
  const dx = q.x - centroX, dy = q.y - centroY;
  if (Math.abs(dx) < 50 && Math.abs(dy) < 50) break;
  await p.mouse.move(1450, 940);
  if (Math.abs(dx) >= 50) { const n = Math.min(14, Math.abs(Math.round(dx / 200))); for (let i = 0; i < n; i++) { await p.mouse.wheel(dx > 0 ? 200 : -200, 0); await p.waitForTimeout(110); } }
  if (Math.abs(dy) >= 50) { const n = Math.min(14, Math.abs(Math.round(dy / 150))); for (let i = 0; i < n; i++) { await p.mouse.wheel(0, dy > 0 ? 150 : -150); await p.waitForTimeout(110); } }
  await p.waitForTimeout(400);
}
await p.mouse.move(1570, 40);            // el cursor fuera de todo nodo, sin tooltips
await p.waitForTimeout(1500);
await p.screenshot({ path: salida, clip: { x: Number(x0), y: Number(y0), width: Number(ancho), height: Number(alto) } });
console.log('ok', salida, await pos(objetivo));
await b.close();
