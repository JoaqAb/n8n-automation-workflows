# n8n Automation Workflows

A collection of n8n workflows documented as case studies. Each folder has the
sanitised export of the workflow, the data schema it uses, and the design
decisions behind it.

Every case here is **self-initiated**: the business and the data are fictional,
built to show the mechanism, not client engagements. The AI extraction and
classification technique they use is already running in production in another
project (the Lokey bot, `lokebox-app`, for a real client, Kieba). See each
README for the detail.

| Workflow | What it solves | Integrations | Status |
|---|---|---|---|
| [01-whatsapp-to-supabase](./01-whatsapp-to-supabase) | NortePeak (fictional solar installer): a lead arrives from a web form or WhatsApp, is normalised, qualified with AI, enriched, stored in Supabase, routed by zone and workload, and followed up | WhatsApp Cloud API, Supabase, Claude API, Slack, Nominatim | Run on 18/10/2026: the six branches and the follow-up, one execution each ([detail](./01-whatsapp-to-supabase#result-and-evidence)) |
| [02-email-invoice-to-supabase](./02-email-invoice-to-supabase) | Andes Freight (fictional freight forwarder): an invoice arrives by email, the fields are extracted with AI, checked against the purchase order, four exceptions are named explicitly, and a person approves what does not match | Email (IMAP), Supabase, Supabase Storage, Claude API, Slack | Run on 18/10/2026: the six branches and the two approval decisions ([detail](./02-email-invoice-to-supabase#result-and-evidence)) |

Both run against the local environment in [`local/`](./local): a database with
these same schemas, the same REST API that Supabase uses, a mailbox and a file
endpoint. The test data is there too, and so are the fixes each node needed
before it would run, one by one, in
[`local/arreglos-2026-10-18.md`](./local/arreglos-2026-10-18.md).

---

Built by [@JoaqAb](https://github.com/JoaqAb) · Portfolio: [lokebox.com/portfolio](https://lokebox.com/portfolio)
