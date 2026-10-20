# 01 · WhatsApp → Supabase — NortePeak (intake y calificación de leads)

> **Nota:** `workflow.json` y `workflow-followup.json` son el export **sanitizado** de los workflows: sin IDs de cuenta, credenciales ni números de teléfono reales.

> **SELF-INITIATED** — construido para demostrar el mecanismo, no un engagement pagado. NortePeak es un negocio ficticio (instalador solar residencial/PyME) y todos los datos son sintéticos. La técnica de extracción/clasificación con IA es la misma que ya está en producción real con un cliente real: ver el caso **AI Messaging & Business Automation** (bot Lokey, `lokebox-app`), construido para Kieba.

## Problema y contexto

NortePeak recibe consultas de dos canales que no se hablan entre sí: un formulario en su sitio web y WhatsApp Business. Cada consulta tiene que resolverse en cuatro preguntas antes de que valga la pena que un vendedor la toque: ¿es un lead nuevo o ya lo tenemos? ¿está dentro de la zona de cobertura? ¿tenemos el dato mínimo para cotizar (consumo mensual)? ¿qué tan calificado está en presupuesto y urgencia? Hoy eso se resuelve a mano, lead por lead, por la misma persona que también tiene que venderle a los leads que ya pasaron el filtro.

El objetivo de este workflow es que un vendedor solo vea un lead cuando ya está calificado, asignado y acompañado de un resumen, nunca el mensaje crudo sin procesar.

## Decisiones de diseño

- **Insertar antes de calificar, nunca después.** El lead se guarda en `leads` (estado `nuevo`) apenas llega, con el payload crudo intacto en `raw_payload`. Todo lo que pasa después (duplicado, fuera de zona, calificación, asignación) son `UPDATE` sobre ese mismo registro, nunca un insert nuevo. Si algo falla a mitad del pipeline, el dato ya está persistido y es recuperable — mismo criterio que usa `bot/claude.js` en `lokebox-app` con el mensaje original del cheque/recibo.
- **Estado como máquina de estados única, no banderas sueltas.** `estado` es una sola columna con un `check` que enumera todos los estados posibles, incluidos los de excepción (`duplicado`, `fuera_de_zona`, `dato_faltante`, `revision_manual`). Nada de columnas booleanas (`es_duplicado`, `fuera_de_zona_flag`) que puedan contradecirse entre sí — el mismo principio que resolvió "El Libro" en `lokebox-app` (una sola fuente de verdad para el estado de un movimiento).
- **Dos workflows, no uno.** El intake (síncrono, vía webhook) y el recordatorio de seguimiento (periódico, vía cron) están en archivos separados. Acoplar un cron de "cada hora" al mismo workflow que responde un webhook en tiempo real es una fuente clásica de timeouts y ejecuciones fantasma; separarlos es más simple de operar y de debuggear.
- **El vendedor nunca ve el mensaje crudo.** El nodo `Alert - Vendedor` manda un resumen estructurado (score, ciudad, consumo, presupuesto estimado, urgencia), no el texto que escribió el lead. Es la misma idea que ya aplica el panel de "Ver como" en `lokebox-app`: la persona humana ve lo que necesita para actuar, no el dato crudo completo.
- **Confianza baja no autocalifica.** Si el modelo devuelve `confianza_ia < 0.7`, el lead va a revisión manual con el motivo explícito (`motivo_revision_manual`), nunca se le asigna un score a ciegas. Mismo patrón que la "pregunta abierta" persistente del bot Lokey real cuando no identifica a un cliente.

## Infraestructura

- **n8n** (self-hosted o cloud) como orquestador.
- **Supabase** (`leads`, `zonas_cobertura`, `vendedores`) como fuente de verdad, acceso solo por `service_role` desde n8n (RLS insert/update-only, ver `schema.sql`).
- **Claude API** (mismo proveedor que el bot Lokey en producción) para la clasificación del lead.
- **Nominatim (OpenStreetMap)** para geocoding de la dirección declarada, API pública sin credencial.
- **WhatsApp Business Cloud API** y **formulario web propio** como los dos canales de entrada.
- **Slack** para las alertas a vendedores y a la cola de revisión manual.

## El workflow nodo por nodo

**Intake (`workflow.json`, 31 nodos):**

1. `Webhook - Form` / `Webhook - WhatsApp` — dos triggers de entrada, un solo pipeline después.
2. `Normalize - Form` / `Normalize - WhatsApp` — cada canal tiene su propio shape de payload (el de WhatsApp además necesita parsear el texto libre del mensaje para sacar ciudad/consumo/urgencia con regex simples); las dos ramas convergen en el mismo esquema de 9 campos.
3. `Merge Channels` → `Insert Lead (Raw)` — se persiste el lead con estado `nuevo` antes de cualquier validación.
4. `Check Duplicate` → `If Duplicate` — busca por `telefono` en los últimos 48hs. Si hay coincidencia: `Mark Duplicado` → `Respond - Duplicado`, fin del flujo para ese lead.
5. `Check Zone` → `If Fuera de Zona` — consulta `zonas_cobertura` por ciudad. Si no está cubierta: `Mark Fuera de Zona` → `Respond - Fuera de Zona`, se registra pero nunca llega a un vendedor.
6. `If Dato Faltante` — si falta `consumo_declarado_kwh`: `Mark Dato Faltante` → `Respond - Dato Faltante`, se le pide el dato al lead en vez de calificar con un vacío.
7. `AI Qualification` → `Parse AI Response` — Claude clasifica tipo de cliente, score, confianza y rango de presupuesto estimado a partir del consumo declarado.
8. `If Confianza Baja` — si `confianza_ia < 0.7`: `Mark Revision Manual` → `Alert - Revision Manual` (Slack) → `Respond - Recibido (Revision)`.
9. `Geocode Address` (en paralelo con `Vendedores Activos`) → `Update Lead - Calificado` — guarda score, confianza, presupuesto estimado y coordenadas.
10. `Assign Salesperson` (nodo de código: vendedor default de la zona, o el de menor `carga_actual` si no hay default) → `Update Lead - Asignado` → `Increment Carga Vendedor`.
11. `Alert - Vendedor` (Slack, resumen calificado) → `Respond - Recibido (OK)`.

**Follow-up (`workflow-followup.json`, 5 nodos):** cron cada hora → busca leads en estado `asignado` con más de 24hs sin pasar a `contactado` y sin recordatorio previo → manda un recordatorio al vendedor por Slack → marca `recordatorio_enviado_en` para no repetir el aviso.

## Edge cases cubiertos por diseño

_(Diseñados y probados contra el esquema y datos sintéticos del seed. Como es self-initiated, no hay incidentes reales de producción que citar — estos son los casos que el flujo está hecho para no romper, no bugs que ya ocurrieron.)_

- **Lead duplicado**: mismo teléfono dentro de 48hs → se marca `duplicado` y se responde sin crear un segundo registro de trabajo para ventas.
- **Fuera de zona**: ciudad ausente del catálogo o con `cobertura = false` (ej. Santiago del Estero en el seed) → nunca llega a un vendedor, pero queda registrado para medir demanda fuera de cobertura.
- **Dato faltante**: sin consumo declarado → se pide el dato explícitamente, nunca se califica con un valor nulo.
- **Confianza baja del modelo**: `confianza_ia < 0.7` → cola de revisión manual con motivo explícito, nunca autocalificación silenciosa.
- **Vendedor sin default en la zona**: el código de asignación cae a round-robin por `carga_actual`, nunca deja un lead calificado sin asignar.
- **Recordatorio duplicado**: el follow-up solo dispara una vez por lead (`recordatorio_enviado_en`), no un aviso por hora mientras el lead siga sin contacto.

## Resultado y evidencia

**Corrido el 18/10/2026** contra el entorno local de `local/` (Postgres con este mismo
`schema.sql` y su `seed.sql`, PostgREST como API, la API de Claude de verdad y Nominatim de
verdad). Las seis ramas del intake y el seguimiento corrieron de punta a punta, una ejecucion
por rama, con los cuerpos que estan versionados en `local/datos/payloads/`.

| rama | datos | como termino |
|---|---|---|
| Fuera de zona | lead de Santiago del Estero, que el catalogo marca sin cobertura | `fuera_de_zona` y respuesta explicita al canal |
| Dato faltante | lead sin consumo declarado | `dato_faltante` y la respuesta pide el kWh |
| Camino feliz | lead de Yerba Buena, 850 kWh, residencial | la IA devolvio score 82 y confianza 0,72; geocodificado, `asignado` a Marina Ponce y su carga paso de 3 a 4 |
| Duplicado | el mismo telefono dentro de las 48 horas | `duplicado`, sin volver a calificar |
| WhatsApp | mensaje con ciudad, direccion y consumo en el texto | normalizado al mismo shape; la IA devolvio confianza 0,6 y fue a `revision_manual` |
| Confianza baja | consulta vaga, sin nombre y con consumo de 1 kWh | `revision_manual` con el motivo `confianza_ia=0.4 por debajo del umbral 0.7` |
| Seguimiento | el lead asignado, con la fecha de asignacion corrida 26 horas atras para no esperar un dia | recordatorio marcado, una sola vez |

**Lo que no corrio, y por que:**

- **Slack.** Los tres nodos de alerta quedan configurados y desactivados: estos casos no tienen
  un workspace propio. En el lienzo se ven en gris.
- **WhatsApp Business Cloud API.** El webhook recibio un cuerpo con la forma que manda esa API,
  no un mensaje que haya pasado por Meta.
- **Supabase hospedado.** La base es la misma, el esquema y las policies son estos, y la API es
  PostgREST, que es el motor que usa Supabase. El proyecto hospedado no entra en la corrida.

Las capturas de los tramos del lienzo estan afuera del repo, en el material del portfolio.
