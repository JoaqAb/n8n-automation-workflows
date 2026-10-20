# 01 · WhatsApp → Supabase: NortePeak (lead intake and qualification)

> **Note:** `workflow.json` and `workflow-followup.json` are the **sanitised** export of the workflows: no account IDs, no credentials, no real phone numbers.

> **SELF-INITIATED**: built to show the mechanism, not a paid engagement. NortePeak is a fictional business (a residential and small business solar installer) and all the data is synthetic. The AI extraction and classification technique is the same one already running in production with a real client: see the **AI Messaging & Business Automation** case (the Lokey bot, `lokebox-app`), built for Kieba.

## The problem

NortePeak gets enquiries from two channels that do not talk to each other: a form on its website and WhatsApp Business. Each enquiry has to answer four questions before it is worth a salesperson's time. Is this a new lead or one we already have? Is it inside the coverage area? Do we have the one figure we need to quote, the monthly consumption? And how qualified is it on budget and urgency? Today that is done by hand, lead by lead, by the same person who also has to sell to the leads that already passed the filter.

The goal of this workflow is that a salesperson only sees a lead once it is qualified, assigned and summarised. Never the raw message.

## Design decisions

- **Insert before qualifying, never after.** The lead is written to `leads` (state `nuevo`) as soon as it arrives, with the raw payload kept intact in `raw_payload`. Everything after that (duplicate, out of area, qualification, assignment) is an `UPDATE` on that same row, never a new insert. If something breaks halfway through the pipeline the data is already saved and can be recovered. This is the same rule `bot/claude.js` uses in `lokebox-app` with the original message of a cheque or a receipt.
- **State as one state machine, not loose flags.** `estado` is a single column with a `check` that lists every possible state, including the exceptions (`duplicado`, `fuera_de_zona`, `dato_faltante`, `revision_manual`). No boolean columns (`es_duplicado`, `fuera_de_zona_flag`) that can contradict each other. It is the same principle behind "El Libro" in `lokebox-app`: one source of truth for the state of a movement.
- **Two workflows, not one.** The intake (synchronous, over a webhook) and the follow-up reminder (periodic, over cron) live in separate files. Coupling an hourly cron to the same workflow that answers a webhook in real time is a classic source of timeouts and ghost executions. Keeping them apart is simpler to run and to debug.
- **The salesperson never sees the raw message.** The `Alert - Vendedor` node sends a structured summary (score, city, consumption, estimated budget, urgency), not the text the lead wrote. It is the same idea as the "Ver como" panel in `lokebox-app`: the person sees what they need in order to act, not the whole raw record.
- **Low confidence does not qualify itself.** If the model returns `confianza_ia < 0.7` the lead goes to manual review with the reason written down (`motivo_revision_manual`). It never gets a score assigned blind. Same pattern as the open question the real Lokey bot keeps asking when it cannot identify a customer.

## Infrastructure

- **n8n** (self-hosted or cloud) as the orchestrator.
- **Supabase** (`leads`, `zonas_cobertura`, `vendedores`) as the source of truth, reached only through `service_role` from n8n (insert and update only RLS, see `schema.sql`).
- **Claude API** (the same provider as the Lokey bot in production) for the lead classification.
- **Nominatim (OpenStreetMap)** to geocode the declared address, a public API with no credential.
- **WhatsApp Business Cloud API** and an **own web form** as the two entry channels.
- **Slack** for the alerts to salespeople and to the manual review queue.

## The workflow, node by node

**Intake (`workflow.json`, 31 nodes):**

1. `Webhook - Form` / `Webhook - WhatsApp`: two entry triggers, a single pipeline after them.
2. `Normalize - Form` / `Normalize - WhatsApp`: each channel has its own payload shape (the WhatsApp one also has to parse the free text of the message to pull out city, consumption and urgency with simple regular expressions). Both branches converge on the same nine field schema.
3. `Merge Channels` → `Insert Lead (Raw)`: the lead is saved with state `nuevo` before any check runs.
4. `Check Duplicate` → `If Duplicate`, looks up `telefono` in the last 48 hours. On a match: `Mark Duplicado` → `Respond - Duplicado`, and the flow ends for that lead.
5. `Check Zone` → `If Fuera de Zona`, queries `zonas_cobertura` by city. If the city is not covered: `Mark Fuera de Zona` → `Respond - Fuera de Zona`. It is recorded, but it never reaches a salesperson.
6. `If Dato Faltante`, if `consumo_declarado_kwh` is missing: `Mark Dato Faltante` → `Respond - Dato Faltante`. The flow asks the lead for the figure instead of qualifying on a blank.
7. `AI Qualification` → `Parse AI Response`: Claude classifies customer type, score, confidence and an estimated budget range from the declared consumption.
8. `If Confianza Baja`, if `confianza_ia < 0.7`: `Mark Revision Manual` → `Alert - Revision Manual` (Slack) → `Respond - Recibido (Revision)`.
9. `Geocode Address` (in parallel with `Vendedores Activos`) → `Update Lead - Calificado`: saves score, confidence, estimated budget and coordinates.
10. `Assign Salesperson` (a code node: the default salesperson for the zone, or the one with the lowest `carga_actual` if there is no default) → `Update Lead - Asignado` → `Increment Carga Vendedor`.
11. `Alert - Vendedor` (Slack, qualified summary) → `Respond - Recibido (OK)`.

**Follow-up (`workflow-followup.json`, 5 nodes):** an hourly cron looks for leads in state `asignado` that have been there more than 24 hours without moving to `contactado` and with no reminder sent, sends the salesperson a reminder over Slack, and marks `recordatorio_enviado_en` so the notice is never repeated.

## Edge cases covered by design

_(Designed and tested against the schema and the synthetic seed data. Because this is self-initiated there are no real production incidents to cite. These are the cases the flow is built not to break on, not bugs that already happened.)_

- **Duplicate lead**: same phone inside 48 hours → marked `duplicado` and answered, without creating a second piece of work for sales.
- **Out of area**: a city missing from the catalogue or with `cobertura = false` (Santiago del Estero in the seed) → it never reaches a salesperson, but it is recorded so demand outside the coverage area can be measured.
- **Missing figure**: no declared consumption → the figure is asked for explicitly, and the lead is never qualified on a null.
- **Low model confidence**: `confianza_ia < 0.7` → manual review queue with the reason written down, never a silent self-qualification.
- **No default salesperson for the zone**: the assignment code falls back to round robin by `carga_actual`, so a qualified lead is never left unassigned.
- **Duplicate reminder**: the follow-up fires once per lead (`recordatorio_enviado_en`), not one notice an hour while the lead stays uncontacted.

## Result and evidence

**Run on 18/10/2026** against the local environment in `local/` (Postgres with this same `schema.sql` and its `seed.sql`, PostgREST as the API, the real Claude API and the real Nominatim). The six intake branches and the follow-up ran end to end, one execution each, with the bodies that are versioned in `local/datos/payloads/`.

| branch | data | how it ended |
|---|---|---|
| Out of area | a lead from Santiago del Estero, which the catalogue marks as not covered | `fuera_de_zona`, with an explicit answer to the channel |
| Missing figure | a lead with no declared consumption | `dato_faltante`, and the answer asks for the kWh |
| Happy path | a lead from Yerba Buena, 850 kWh, residential | the AI returned score 82 and confidence 0.72; geocoded, `asignado` to Marina Ponce, and her workload went from 3 to 4 |
| Duplicate | the same phone inside 48 hours | `duplicado`, with no second qualification |
| WhatsApp | a message with city, address and consumption in the text | normalised to the same shape; the AI returned confidence 0.6 and it went to `revision_manual` |
| Low confidence | a vague enquiry, no name and a consumption of 1 kWh | `revision_manual` with the reason `confianza_ia=0.4 por debajo del umbral 0.7` |
| Follow-up | the assigned lead, with the assignment date moved 26 hours back so there was no need to wait a day | reminder marked, once only |

**What did not run, and why:**

- **Slack.** The three alert nodes are configured and switched off: these cases have no workspace of their own. They show grey on the canvas.
- **WhatsApp Business Cloud API.** The webhook received a body shaped the way that API sends it, not a message that actually went through Meta.
- **Hosted Supabase.** The database is the same, the schema and the policies are these, and the API is PostgREST, which is the engine Supabase uses. The hosted project is not part of the run.

The captures of the canvas sections live outside this repo, in the portfolio material.
