# 02 · Email → Supabase: Andes Freight (invoice extraction and validation)

> **Note:** `workflow.json` and `workflow-approval.json` are the **sanitised** export of the workflows: no account IDs, no credentials, no real supplier data.

> **SELF-INITIATED**: built to show the mechanism, not a paid engagement. Andes Freight is a fictional business (freight forwarding) and all the data is synthetic. The AI extraction technique is the same one already running in production with a real client: see the **AI Messaging & Business Automation** case (the Lokey bot, `lokebox-app`), which tells receipts from cheques with this same mechanism.

## The problem

Andes Freight receives supplier invoices by email, as a PDF or a photo attached. Today somebody in accounts payable opens them one by one, types them by hand against the matching purchase order, and when something does not add up (no PO, the amount does not match, the currency is not the expected one) they sort it out as they go, leaving no record that there was an exception or who approved it.

The goal of this workflow is that an invoice arrives, is extracted and checked against the PO on its own, and that a person only touches it when there is a concrete, named reason to. Never to retype a figure the AI could already read.

## Design decisions

- **Upload the attachment before extracting anything.** `Upload Attachment` puts the PDF or image into Supabase Storage and `Insert Factura (Raw)` saves the row with that URL before the AI is called. If the extraction fails the invoice is not lost: it stays in `recibida` with the attachment reachable. It is the same "save before processing" rule as case 01 (NortePeak) and as `bot/claude.js` in real production.
- **Four exceptions, one meeting point.** Low extraction confidence, no PO, an amount that does not add up, an unexpected currency: four different paths that reach the same state (`pendiente_aprobacion`) with a specific `motivo_excepcion`. Nothing is ever approved by elimination or by silence.
- **Approval is a separate workflow.** `workflow.json` never waits for a live human answer (that would block the n8n execution indefinitely). It leaves the invoice in `pendiente_aprobacion` and notifies. The actual decision, approve or reject, is taken by `workflow-approval.json`, fired by a webhook when somebody in accounts payable decides. Same separation as the intake and follow-up in case 01.
- **Reconciling is a verb, not a default state.** An invoice reaches `conciliada` through two explicit paths only: automatically, when it passed the four checks with no exception, or by a person approving the exception. There is never a third path that marks it reconciled just in case.
- **Dedup by supplier plus invoice number, with a conditional unique index.** The `idx_facturas_proveedor_numero` index in `schema.sql` explicitly leaves out invoices already rejected or marked duplicate, so a legitimate retry after a correction is not blocked.

## Infrastructure

- **n8n** (self-hosted or cloud) as the orchestrator, with two workflows: intake and validation (fired by email) and approval (fired by a webhook).
- **Supabase** (`facturas`, `ordenes_compra`, `proveedores`) as the source of truth, reached only through `service_role` (insert and update only RLS).
- **Supabase Storage** for the original attachments.
- **Claude API** (the same provider as the Lokey bot in production) for the vision extraction.
- **IMAP** (a dedicated mailbox) as the entry channel.
- **Slack** for the exception and reconciliation alerts.

## The workflow, node by node

**Intake and validation (`workflow.json`, 25 nodes):**

1. `Email Trigger - Facturas` → `Upload Attachment` → `Insert Factura (Raw)`: saved with state `recibida` before any AI runs.
2. `Extract With AI` (Claude, vision over the attachment) → `Parse AI Response` → `Update Factura - Extraida`.
3. `Check Duplicate` → `If Duplicate`, same supplier and same invoice number already loaded: `Mark Duplicada` → `Notify - Duplicada`, end.
4. `If Confianza Baja` (`confianza_extraccion < 0.75`): `Mark Excepcion Baja Confianza` → joins `Mark Pendiente Aprobacion`.
5. `Check OC` → `If Sin OC`: no purchase order attached → `Mark Excepcion Sin OC` → joins `Mark Pendiente Aprobacion`.
6. `Compute Diff Monto` (a code node, the percentage difference against the PO) → `If Monto Diff` (over 5%): `Mark Excepcion Monto` → joins `Mark Pendiente Aprobacion`.
7. `Check Proveedor Moneda` → `If Moneda Distinta` (extracted currency is not the one the supplier bills in): `Mark Excepcion Moneda` → joins `Mark Pendiente Aprobacion`.
8. If it passed the four checks with no exception: `Mark Conciliada` → `Notify - Conciliada`, end.
9. On any exception: `Mark Pendiente Aprobacion` → `Alert - Pendiente Aprobacion` (Slack, with the specific reason), and this workflow ends. The decision carries on in `workflow-approval.json`.

**Approval decision (`workflow-approval.json`, 7 nodes):** a webhook with `{factura_id, decision, usuario}`. On approve: `Update Factura - Aprobada` → `Update Factura - Conciliada` → answers OK. On reject: `Update Factura - Rechazada` → `Notify - Rechazada` → answers OK.

## Edge cases covered by design

_(Designed and tested against the schema and the synthetic seed data. Because this is self-initiated there are no real production incidents to cite.)_

- **Duplicate invoice**: same supplier and invoice number already loaded → `duplicada`, with no second exception for accounts payable.
- **Low confidence extraction**: `confianza_extraccion < 0.75` → an explicit exception. A doubtful amount or supplier is never guessed.
- **No PO attached**: `numero_oc` empty or missing from the catalogue → an explicit exception. Nothing is reconciled without a purchase order.
- **Amount that does not add up**: more than 5% difference against the PO → an exception with the exact percentage in the reason.
- **Unexpected currency**: the supplier bills in a currency other than the one on file (in the seed, Global Reefer Parts always bills in USD) → an explicit exception, never a silent automatic conversion.
- **Rejection**: a rejected invoice keeps that final state and the person responsible (`aprobado_por`). It never returns to `pendiente_aprobacion` on its own.

## Result and evidence

**Run on 18/10/2026** against the local environment in `local/` (Postgres with this same `schema.sql` and its `seed.sql`, PostgREST as the API, a local IMAP mailbox and the real Claude API). The sample invoices are generated by `local/datos/facturas.py` and are fictional.

The email trigger ran for real: each invoice arrived as a mail with its attachment, the original file was saved **before** the AI touched it, and only then was it extracted.

| run | invoice | how it ended |
|---|---|---|
| Happy path | 0001-00004821, Combustibles del Litoral, ARS 185,000 against PO-2026-0441 | extracted with confidence 0.98 and `conciliada` |
| Amount does not add up | 0002-00000517, ARS 72,400 against a PO of ARS 62,000 | `excepcion_monto`, reason `difiere 16.8% de la OC` |
| No purchase order | 0002-00000533, OC-2026-9144, which does not exist | `excepcion_sin_oc` |
| Unexpected currency | 0002-00000540, USD from a supplier that bills in ARS | `excepcion_moneda`, with both currencies in the reason |
| Low confidence | a small, tilted, washed out scan | the extraction returned 0.15 and it stayed in `excepcion_baja_confianza` |
| Duplicate | the same invoice sent again after being rejected | `duplicada`, with no second validation |
| Human approval | the two decisions over the webhook | approving leaves it `conciliada` with the person responsible; rejecting leaves it `rechazada` |

The four exceptions all end in `pendiente_aprobacion` with their reason written down, which is the point of the case: no invoice moves forward by silence.

**What did not run, and why:**

- **Slack.** The four notice nodes are configured and switched off: this case has no workspace of its own. They show grey on the canvas.
- **Supabase Storage.** The attachment is uploaded to a local endpoint with the same request and response shape. The hosted bucket is not part of the run.
- **Hosted Supabase.** The database is the same, the schema and the policies are these, and the API is PostgREST, which is the engine Supabase uses.

The captures of the canvas sections live outside this repo, in the portfolio material.
