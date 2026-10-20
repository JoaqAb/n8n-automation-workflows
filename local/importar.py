"""Pone en n8n los cuatro workflows tal como quedaron en el repo, mas lo que solo vale local.

Lo que se le agrega a la copia local, y no va al repo:
  - las credenciales,
  - los nodos de Slack desactivados,
  - el host del Storage apuntado a la puerta local en vez del placeholder.
"""
import json
import n8napi as api

REPO = "/home/joaquin/proyectos/n8n-automation-workflows/"
MAPA = {
    "wf01intake": (REPO + "01-whatsapp-to-supabase/workflow.json", "01"),
    "wf01follow": (REPO + "01-whatsapp-to-supabase/workflow-followup.json", "01"),
    "wf02intake": (REPO + "02-email-invoice-to-supabase/workflow.json", "02"),
    "wf02approve": (REPO + "02-email-invoice-to-supabase/workflow-approval.json", "02"),
}
CREDS = json.load(open("creds.json"))
SLACK = {"01": "Slack NortePeak (sin correr)", "02": "Slack Andes Freight (sin correr)"}
GW = "http://pf-gw:8080"
AI = {"AI Qualification", "Extract With AI"}


def ref(nombre):
    return {"id": CREDS[nombre]["id"], "name": nombre}


api.entrar()
for wid, (ruta, caso) in MAPA.items():
    repo = json.load(open(ruta, encoding="utf8"))
    vivo = api.flujo(wid)
    locales = []
    for n in repo["nodes"]:
        t = n["type"].replace("n8n-nodes-base.", "")
        p = n.setdefault("parameters", {})
        if t == "supabase":
            n["credentials"] = {"supabaseApi": ref("Supabase local (portfolio)")}
        elif t == "slack":
            n["credentials"] = {"slackApi": ref(SLACK[caso])}
            n["disabled"] = True
            locales.append((n["name"], "desactivado"))
        elif t == "emailReadImap":
            n["credentials"] = {"imap": ref("Buzon facturas local (IMAP)")}
        elif t == "httpRequest" and p.get("genericAuthType") == "httpHeaderAuth":
            n["credentials"] = {"httpHeaderAuth": ref(
                "Claude API (x-api-key)" if n["name"] in AI else "Supabase Storage local (bearer)")}
            if "<project>.supabase.co" in p.get("url", ""):
                p["url"] = p["url"].replace("https://<project>.supabase.co", GW)
                locales.append((n["name"], "host del Storage local"))
    vivo["nodes"] = repo["nodes"]
    vivo["connections"] = repo["connections"]
    vivo["settings"] = repo.get("settings", {"executionOrder": "v1"})
    c, res = api.guardar(wid, vivo)
    print("%-12s http %s | %d nodos | local: %s" % (
        wid, c, len(repo["nodes"]), ", ".join("%s (%s)" % x for x in locales) or "nada"))
    if c != 200:
        print("   ", json.dumps(res)[:300])
