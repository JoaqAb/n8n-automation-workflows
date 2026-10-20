# 02 · Email → Supabase — Andes Freight (extracción y validación de facturas)

> **Nota:** `workflow.json` y `workflow-approval.json` son el export **sanitizado** de los workflows: sin IDs de cuenta, credenciales ni datos reales de proveedores.

> **SELF-INITIATED** — construido para demostrar el mecanismo, no un engagement pagado. Andes Freight es un negocio ficticio (freight forwarding) y todos los datos son sintéticos. La técnica de extracción con IA es la misma que ya está en producción real con un cliente real: ver el caso **AI Messaging & Business Automation** (bot Lokey, `lokebox-app`), que distingue recibos de cheques con el mismo mecanismo.

## Problema y contexto

Andes Freight recibe facturas de proveedores por email, como PDF o foto adjunta. Hoy alguien de cuentas a pagar las abre una por una, las tipea a mano contra la orden de compra correspondiente, y si algo no cierra (no hay OC, el monto no coincide, la moneda no es la esperada) lo resuelve sobre la marcha, sin que quede un registro de que hubo una excepción ni de quién la aprobó.

El objetivo de este workflow es que una factura entre, se extraiga y se valide sola contra la OC, y que una persona solo la toque cuando hay una razón concreta y nombrada para hacerlo — nunca para re-tipear un dato que la IA ya pudo leer bien.

## Decisiones de diseño

- **Subir el adjunto antes de extraer nada.** `Upload Attachment` sube el PDF/imagen a Supabase Storage y `Insert Factura (Raw)` persiste el registro con esa URL antes de llamar a la IA. Si la extracción falla, la factura no se pierde, queda en `recibida` con el adjunto accesible — mismo criterio de "persistir antes de procesar" que el caso 01 (NortePeak) y que `bot/claude.js` en producción real.
- **Cuatro excepciones, un solo punto de confluencia.** Baja confianza de extracción, sin OC, monto que no cierra, moneda inesperada: las cuatro son caminos distintos que llegan al mismo estado (`pendiente_aprobacion`) con un `motivo_excepcion` específico. Nunca se autoaprueba nada por descarte ni por silencio.
- **La aprobación es un workflow separado.** `workflow.json` nunca espera una respuesta humana en vivo (eso bloquearía la ejecución de n8n indefinidamente); deja la factura en `pendiente_aprobacion` y notifica. La decisión real (aprobar/rechazar) la toma `workflow-approval.json`, disparado por un webhook cuando alguien de cuentas a pagar decide — mismo patrón de separación que el intake/follow-up del caso 01.
- **Conciliar es un verbo, no un estado por defecto.** Una factura solo pasa a `conciliada` por dos caminos explícitos: automático (pasó las 4 validaciones sin excepción) o humano (alguien aprobó la excepción). Nunca hay un tercer camino que la marque conciliada "por las dudas".
- **Dedup por proveedor + número de factura, con índice único condicional.** El índice `idx_facturas_proveedor_numero` en `schema.sql` excluye explícitamente las facturas ya rechazadas o duplicadas, para no bloquear un reintento legítimo después de una corrección.

## Infraestructura

- **n8n** (self-hosted o cloud) como orquestador, dos workflows: intake/validación (disparado por email) y aprobación (disparado por webhook).
- **Supabase** (`facturas`, `ordenes_compra`, `proveedores`) como fuente de verdad, acceso solo por `service_role` (RLS insert/update-only).
- **Supabase Storage** para los adjuntos originales.
- **Claude API** (mismo proveedor que el bot Lokey en producción) para la extracción con visión.
- **IMAP** (casilla de email dedicada) como canal de entrada.
- **Slack** para las alertas de excepción/conciliación.

## El workflow nodo por nodo

**Intake y validación (`workflow.json`, 25 nodos):**

1. `Email Trigger - Facturas` → `Upload Attachment` → `Insert Factura (Raw)` — persiste con estado `recibida` antes de cualquier IA.
2. `Extract With AI` (Claude, visión sobre el adjunto) → `Parse AI Response` → `Update Factura - Extraida`.
3. `Check Duplicate` → `If Duplicate` — mismo proveedor + mismo número de factura ya cargado: `Mark Duplicada` → `Notify - Duplicada`, fin.
4. `If Confianza Baja` (`confianza_extraccion < 0.75`): `Mark Excepcion Baja Confianza` → confluye en `Mark Pendiente Aprobacion`.
5. `Check OC` → `If Sin OC`: sin orden de compra asociada → `Mark Excepcion Sin OC` → confluye en `Mark Pendiente Aprobacion`.
6. `Compute Diff Monto` (nodo de código: % de diferencia contra la OC) → `If Monto Diff` (> 5%): `Mark Excepcion Monto` → confluye en `Mark Pendiente Aprobacion`.
7. `Check Proveedor Moneda` → `If Moneda Distinta` (moneda extraída ≠ moneda esperada del proveedor): `Mark Excepcion Moneda` → confluye en `Mark Pendiente Aprobacion`.
8. Si pasó las 4 validaciones sin excepción: `Mark Conciliada` → `Notify - Conciliada`, fin.
9. Cualquier excepción: `Mark Pendiente Aprobacion` → `Alert - Pendiente Aprobacion` (Slack con el motivo específico), fin de este workflow — la decisión sigue en `workflow-approval.json`.

**Decisión de aprobación (`workflow-approval.json`, 7 nodos):** webhook con `{factura_id, decision, usuario}` → si aprueba: `Update Factura - Aprobada` → `Update Factura - Conciliada` → responde OK. Si rechaza: `Update Factura - Rechazada` → `Notify - Rechazada` → responde OK.

## Edge cases cubiertos por diseño

_(Diseñados y probados contra el esquema y datos sintéticos del seed. Como es self-initiated, no hay incidentes reales de producción que citar.)_

- **Factura duplicada**: mismo proveedor + número de factura ya cargado → `duplicada`, no genera una segunda excepción de cuentas a pagar.
- **Extracción de baja confianza**: `confianza_extraccion < 0.75` → excepción explícita, nunca se adivina un monto o proveedor dudoso.
- **Sin OC asociada**: `numero_oc` vacío o inexistente en el catálogo → excepción explícita, nunca se concilia sin orden de compra.
- **Monto que no cierra**: diferencia mayor al 5% contra la OC → excepción con el porcentaje exacto en el motivo.
- **Moneda inesperada**: el proveedor factura en una moneda distinta a la que tiene registrada (seed: Global Reefer Parts factura siempre en USD) → excepción explícita, nunca conversión automática silenciosa.
- **Rechazo**: la factura rechazada queda con ese estado final y su responsable (`aprobado_por`), nunca vuelve a `pendiente_aprobacion` sola.

## Resultado y evidencia

**Corrido el 18/10/2026** contra el entorno local de `local/` (Postgres con este mismo
`schema.sql` y su `seed.sql`, PostgREST como API, un buzon IMAP local y la API de Claude de
verdad). Las facturas de muestra las genera `local/datos/facturas.py` y son ficticias.

El disparador de correo corrio de verdad: cada factura entro como un mail con su adjunto, el
archivo original quedo guardado **antes** de que la IA lo tocara, y recien despues se extrajo.

| corrida | factura | como termino |
|---|---|---|
| Camino feliz | 0001-00004821, Combustibles del Litoral, ARS 185.000 contra la OC-2026-0441 | extraida con confianza 0,98 y `conciliada` |
| Monto que no cierra | 0002-00000517, ARS 72.400 contra una OC de ARS 62.000 | `excepcion_monto`, motivo `difiere 16.8% de la OC` |
| Sin orden de compra | 0002-00000533, OC-2026-9144, que no existe | `excepcion_sin_oc` |
| Moneda inesperada | 0002-00000540, USD de un proveedor que factura en ARS | `excepcion_moneda` con las dos monedas en el motivo |
| Confianza baja | un escaneo chico, torcido y lavado | la extraccion devolvio 0,15 y quedo en `excepcion_baja_confianza` |
| Duplicada | la misma factura reenviada despues de ser rechazada | `duplicada`, sin volver a validar |
| Aprobacion humana | las dos decisiones por webhook | aprobar deja `conciliada` con su responsable; rechazar deja `rechazada` |

Las cuatro excepciones terminan en `pendiente_aprobacion` con su motivo escrito, que es el
punto del caso: ninguna factura avanza por silencio.

**Lo que no corrio, y por que:**

- **Slack.** Los cuatro nodos de aviso quedan configurados y desactivados: este caso no tiene un
  workspace propio. En el lienzo se ven en gris.
- **Supabase Storage.** El adjunto se sube a un endpoint local con la misma forma de pedido y de
  respuesta. El bucket hospedado no entra en la corrida.
- **Supabase hospedado.** La base es la misma, el esquema y las policies son estos, y la API es
  PostgREST, que es el motor que usa Supabase.

Las capturas de los tramos del lienzo estan afuera del repo, en el material del portfolio.
