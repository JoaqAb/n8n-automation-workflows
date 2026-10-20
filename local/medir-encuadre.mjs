// Mide, sobre pixeles reales, cuanto mide la etiqueta de un nodo en el lienzo de n8n
// a cada nivel de zoom, y recorta la etiqueta para medir su tinta.
import { chromium } from 'playwright';
import { readFileSync, mkdirSync } from 'node:fs';

const txt = readFileSync('/tmp/claude-1000/-home-joaquin-proyectos/93f977d9-f8dc-41c2-967b-ba835c581639/scratchpad/n8n-local.txt', 'utf8');
const email = txt.match(/email:\s*(\S+)/)[1], pass = txt.match(/pass:\s*(\S+)/)[1];
const OUT = '/tmp/claude-1000/-home-joaquin-proyectos/4e387313-02e0-4d1c-ad5e-fd6ecc95b036/scratchpad/medidas';
mkdirSync(OUT, { recursive: true });

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
await p.goto('http://localhost:5678/workflow/wf02approve', { waitUntil: 'domcontentloaded' });
await p.waitForTimeout(6000);
await p.keyboard.press('Escape');
await p.mouse.click(1450, 940);
await p.waitForTimeout(600);
await p.keyboard.press('1');
await p.waitForTimeout(1500);

const datos = [];
for (let z = 0; z <= 8; z++) {
  if (z > 0) { await p.keyboard.press('='); await p.waitForTimeout(500); }
  await p.mouse.move(1570, 40);
  await p.waitForTimeout(500);
  const m = await p.evaluate(() => {
    const t = document.querySelector('.vue-flow__transform');
    const escala = t ? Number((t.style.transform.match(/scale\(([\d.]+)\)/) || [0, 1])[1]) : 1;
    const nodos = [...document.querySelectorAll('[data-test-id="canvas-node"]')];
    if (!nodos.length) return { escala, n: 0 };
    const etiquetas = nodos.map((n) => {
      const nombre = n.getAttribute('data-node-name');
      return [...n.querySelectorAll('*')].find((e) => e.children.length === 0 && e.textContent.trim() === nombre);
    });
    const et = etiquetas.find(Boolean);
    const r = et.getBoundingClientRect();
    const cs = getComputedStyle(et);
    const rn = nodos[0].getBoundingClientRect();
    // separacion entre nodos consecutivos en pantalla
    const xs = nodos.map((n) => n.getBoundingClientRect().x).sort((a, b) => a - b);
    let sep = 0;
    for (let i = 1; i < xs.length; i++) { const d = xs[i] - xs[i - 1]; if (d > 5 && (!sep || d < sep)) sep = d; }
    return {
      escala, n: nodos.length, fontPx: parseFloat(cs.fontSize),
      etiqueta: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height), texto: et.textContent.trim() },
      nodoAncho: Math.round(rn.width), separacion: Math.round(sep),
    };
  });
  if (!m.n) continue;
  const e = m.etiqueta;
  if (e.x > 0 && e.y > 0 && e.x + e.w < 1600 && e.y + e.h < 1000) {
    await p.screenshot({ path: `${OUT}/etiqueta-z${z}.png`, clip: { x: e.x, y: e.y, width: Math.max(e.w, 10), height: Math.max(e.h, 10) } });
  }
  datos.push({ z, ...m });
  console.log(JSON.stringify({ z, escala: m.escala, fontPx: m.fontPx, sep: m.separacion, nodo: m.nodoAncho, etiqueta: e.texto }));
}
await b.close();
