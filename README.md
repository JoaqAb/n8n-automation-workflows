# n8n Automation Workflows

Colección de workflows de n8n documentados como case studies.
Cada carpeta incluye el export sanitizado del workflow, el esquema de datos
que usa y la documentación de las decisiones de diseño detrás de él.

Todos los casos de esta colección son **self-initiated**: negocio y datos ficticios, construidos para demostrar el mecanismo, no engagements de cliente real. La técnica de extracción/clasificación con IA que usan ya está probada en producción real en otro proyecto (bot Lokey, `lokebox-app`, cliente real Kieba) — ver cada README para el detalle.

| Workflow | Qué resuelve | Integraciones | Estado |
|---|---|---|---|
| [01-whatsapp-to-supabase](./01-whatsapp-to-supabase) | NortePeak (instalador solar, ficticio): lead de formulario web o WhatsApp → normalización → calificación con IA → enrichment → Supabase → routing por zona/carga → alerta y seguimiento | WhatsApp Cloud API, Supabase, Claude API, Slack, Nominatim | Corrido el 18/10/2026: las seis ramas y el seguimiento, una ejecución por rama ([detalle](./01-whatsapp-to-supabase#resultado-y-evidencia)) |
| [02-email-invoice-to-supabase](./02-email-invoice-to-supabase) | Andes Freight (freight forwarding, ficticio): factura por email → extracción con IA → validación contra orden de compra → 4 excepciones explícitas → cola de aprobación humana → conciliación | Email (IMAP), Supabase, Supabase Storage, Claude API, Slack | Corrido el 18/10/2026: las seis ramas y las dos decisiones de aprobación ([detalle](./02-email-invoice-to-supabase#resultado-y-evidencia)) |
| 03-placeholder | Sin asignar | — | Pendiente |

Los dos corren contra el entorno local que vive en [`local/`](./local): una base con estos
mismos esquemas, la misma API REST que usa Supabase, un buzón de correo y un endpoint de
archivos. Ahí están también los datos de prueba y los arreglos que hubo que hacerle a los
nodos para que corrieran, uno por uno, en [`local/arreglos-2026-10-18.md`](./local/arreglos-2026-10-18.md).

---

Hecho por [@JoaqAb](https://github.com/JoaqAb) · Portfolio: [lokebox.com/portfolio](https://lokebox.com/portfolio)
