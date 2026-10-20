import n8napi as api, json, sys
from flatted import cargar
def ver(eid, mostrar=True):
    c,d=api.pedir("GET","/rest/executions/"+str(eid))
    d=d["data"]; datos=d.get("data")
    if isinstance(datos,str): datos=cargar(datos)
    rd=datos["resultData"]; run=rd["runData"]
    if mostrar:
        print("== exec %s | %s | %s | %s"%(eid,d["status"],d["mode"],d.get("workflowId")))
        for nombre,corridas in run.items():
            r=corridas[0]
            sal=(r.get("data") or {}).get("main") or []
            items=sum(len(x or []) for x in sal)
            ramas=[len(x or []) for x in sal]
            e=r.get("error") or {}
            print("   %-34s items=%-3s ramas=%-12s %s"%(nombre,items,ramas,(e.get("message") or "")[:110]))
        err=rd.get("error")
        if err: print("   >> ERROR:",(err.get("message") or "")[:200],"| nodo:",(err.get("node") or {}).get("name"))
    return d,run,rd
if __name__=="__main__":
    api.entrar()
    for eid in sys.argv[1:]: ver(eid)
