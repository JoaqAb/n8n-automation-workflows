"""Compara los JSON del repo con la version publicada en n8n, ignorando lo declarado como local."""
import json, n8napi as api
REPO="/home/joaquin/proyectos/n8n-automation-workflows/"
MAPA={"wf01intake":REPO+"01-whatsapp-to-supabase/workflow.json",
      "wf01follow":REPO+"01-whatsapp-to-supabase/workflow-followup.json",
      "wf02intake":REPO+"02-email-invoice-to-supabase/workflow.json",
      "wf02approve":REPO+"02-email-invoice-to-supabase/workflow-approval.json"}
LOCAL=("credentials","disabled")
api.entrar()
todo=True
for wid,ruta in MAPA.items():
    w=api.flujo(wid)
    pub=w.get("activeVersion") or {}
    nodos_pub={n["name"]:n for n in pub.get("nodes",[])}
    repo=json.load(open(ruta,encoding="utf8"))
    difs=[]
    if w.get("activeVersionId")!=w.get("versionId"): difs.append("la version publicada no es la actual")
    for n in repo["nodes"]:
        p=nodos_pub.get(n["name"])
        if not p: difs.append("falta en la publicada: "+n["name"]); continue
        a=json.loads(json.dumps(n["parameters"])); b=json.loads(json.dumps(p["parameters"]))
        if "url" in a and "<project>.supabase.co" in str(a["url"]):
            a["url"]=a["url"].replace("https://<project>.supabase.co","http://pf-gw:8080")
        if a!=b: difs.append("parametros distintos: "+n["name"])
        if n.get("alwaysOutputData") != p.get("alwaysOutputData"): difs.append("alwaysOutputData: "+n["name"])
    if json.dumps(repo["connections"],sort_keys=True)!=json.dumps(pub.get("connections"),sort_keys=True):
        difs.append("conexiones distintas")
    desact=[k for k,v in nodos_pub.items() if v.get("disabled")]
    print("%-12s %s | desactivados: %s"%(wid,"IGUAL" if not difs else "DIFERENCIAS: "+"; ".join(difs), ", ".join(desact) or "ninguno"))
    todo = todo and not difs
print("\nel repo es lo que corre:", todo)
