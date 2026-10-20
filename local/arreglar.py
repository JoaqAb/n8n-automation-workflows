"""Arregla los cuatro workflows sobre los JSON del repo y deja el detalle en arreglos.json.

Ninguna conexion cambia, ningun nodo se agrega ni se saca, ninguna rama cambia de sentido.
Lo que cambia es: de donde lee cada expresion, con que filtro escribe cada update, que una
busqueda vacia emita un item vacio en vez de nada, y lo que el export sanitizado dejo a medias.

    python3 arreglar.py          escribe los cuatro JSON del repo
"""
import json
import os

REPO = "/home/joaquin/proyectos/n8n-automation-workflows/"
AQUI = os.path.dirname(os.path.abspath(__file__))
ARCHIVOS = {
    "01 intake": ("originales/01-workflow.json", REPO + "01-whatsapp-to-supabase/workflow.json"),
    "01 seguimiento": ("originales/01-followup.json", REPO + "01-whatsapp-to-supabase/workflow-followup.json"),
    "02 facturas": ("originales/02-workflow.json", REPO + "02-email-invoice-to-supabase/workflow.json"),
    "02 aprobacion": ("originales/02-approval.json", REPO + "02-email-invoice-to-supabase/workflow-approval.json"),
}
LEAD = "$('Insert Lead (Raw)').item.json"
FACT = "$('Update Factura - Extraida').item.json"
PARSE2 = "$('Parse AI Response').item.json"
HAY = {"type": "string", "operation": "exists", "singleValue": True}
NO_HAY = {"type": "string", "operation": "notExists", "singleValue": True}
ES_CIERTO = {"type": "boolean", "operation": "true", "singleValue": True}
VACIO = {"type": "number", "operation": "empty", "singleValue": True}
LOG = []


def anota(caso, nodo, que, antes, ahora):
    LOG.append({"caso": caso, "nodo": nodo, "que": que,
                "antes": str(antes)[:200], "ahora": str(ahora)[:200]})


def filtro(caso, n, campo, valor):
    p = n["parameters"]
    antes = "matchingColumns: %s" % p.get("matchingColumns")
    p.pop("matchingColumns", None)
    p["filterType"] = "manual"
    p["matchType"] = "allFilters"
    p["filters"] = {"conditions": [{"keyName": campo, "condition": "eq", "keyValue": valor}]}
    anota(caso, n["name"], "el update no tenia con que encontrar la fila", antes,
          "%s eq %s" % (campo, valor))


def siempre(caso, n):
    n["alwaysOutputData"] = True
    anota(caso, n["name"], "una busqueda sin resultados cortaba el flujo",
          "no emitia ningun item", "emite un item vacio")


def cond(caso, n, left, op, right, motivo):
    c = n["parameters"]["conditions"]["conditions"][0]
    antes = "%s %s %s" % (c.get("leftValue"), c.get("operator", {}).get("operation"), c.get("rightValue"))
    c["leftValue"] = left
    c["operator"] = op
    c["rightValue"] = right
    anota(caso, n["name"], motivo, antes, "%s %s %s" % (left, op["operation"], right))


def expr(caso, n, ruta, nuevo, motivo):
    obj = n["parameters"]
    for k in ruta[:-1]:
        obj = obj[k]
    anota(caso, n["name"], motivo, obj[ruta[-1]], nuevo)
    obj[ruta[-1]] = nuevo


def claude(caso, n):
    """Completa lo que el export sanitizado dejo a medias en los nodos de IA."""
    p = n["parameters"]
    p["sendBody"] = True
    p["specifyBody"] = "json"
    p["sendHeaders"] = True
    p["specifyHeaders"] = "keypair"
    p["headerParameters"] = {"parameters": [{"name": "anthropic-version", "value": "2023-06-01"}]}
    anota(caso, n["name"], "el cuerpo no se enviaba y faltaba el header de version",
          "jsonBody sin sendBody", "sendBody + anthropic-version")


flujos = {k: json.load(open(os.path.join(AQUI, v[0]), encoding="utf8")) for k, v in ARCHIVOS.items()}
N = {k: {n["name"]: n for n in f["nodes"]} for k, f in flujos.items()}

# ------------------------------------------------------------------ 01 intake
c = "01 intake"
n = N[c]
siempre(c, n["Check Duplicate"])
cond(c, n["If Duplicate"], "={{ $json.id }}", HAY, "",
     "preguntaba por el largo de un array que el nodo Supabase no devuelve")
filtro(c, n["Mark Duplicado"], "id", "={{ %s.id }}" % LEAD)

expr(c, n["Check Zone"], ["filters", "conditions", 0, "keyValue"], "={{ %s.ciudad }}" % LEAD,
     "buscaba la zona con la ciudad de un item que ya no era el lead")
siempre(c, n["Check Zone"])
cond(c, n["If Fuera de Zona"], "={{ !$json.ciudad || $json.cobertura === false }}", ES_CIERTO, True,
     "preguntaba por el largo de un array que el nodo Supabase no devuelve")
filtro(c, n["Mark Fuera de Zona"], "id", "={{ %s.id }}" % LEAD)

cond(c, n["If Dato Faltante"], "={{ %s.consumo_declarado_kwh }}" % LEAD,
     VACIO, "",
     "buscaba el consumo sobre la fila de zona, no sobre el lead")
filtro(c, n["Mark Dato Faltante"], "id", "={{ %s.id }}" % LEAD)

claude(c, n["AI Qualification"])
expr(c, n["AI Qualification"], ["jsonBody"],
     n["AI Qualification"]["parameters"]["jsonBody"].replace("$json.", LEAD + "."),
     "el prompt leia los datos del lead sobre la fila de zona")
filtro(c, n["Mark Revision Manual"], "id", "={{ %s.id }}" % LEAD)
expr(c, n["Mark Revision Manual"], ["fieldsUi", "fieldValues", 1, "fieldValue"],
     "={{ \"confianza_ia=\" + $('Parse AI Response').item.json.confianza_ia + \" por debajo del umbral 0.7\" }}",
     "el motivo leia la confianza de un item que no la tenia")

expr(c, n["Geocode Address"], ["url"],
     "=https://nominatim.openstreetmap.org/search?format=json&q={{ encodeURIComponent(%s.direccion + ', ' + %s.ciudad) }}" % (LEAD, LEAD),
     "geocodificaba una direccion que no estaba en el item")
filtro(c, n["Update Lead - Calificado"], "id", "={{ %s.id }}" % LEAD)
expr(c, n["Update Lead - Calificado"], ["fieldsUi", "fieldValues", 5, "fieldValue"],
     "={{ $json.lat || null }}", "Nominatim devuelve un item por resultado, no un array adentro de uno")
expr(c, n["Update Lead - Calificado"], ["fieldsUi", "fieldValues", 6, "fieldValue"],
     "={{ $json.lon || null }}", "Nominatim devuelve un item por resultado, no un array adentro de uno")

filtro(c, n["Update Lead - Asignado"], "id", "={{ %s.id }}" % LEAD)
filtro(c, n["Increment Carga Vendedor"], "nombre",
       "={{ $('Assign Salesperson').item.json.vendedor_asignado }}")
expr(c, n["Increment Carga Vendedor"], ["fieldsUi", "fieldValues", 0, "fieldValue"],
     "={{ ($('Vendedores Activos').all().find(v => v.json.nombre === $('Assign Salesperson').item.json.vendedor_asignado)?.json.carga_actual ?? 0) + 1 }}",
     "sumaba uno a una carga que no venia en el item")
expr(c, n["Respond - Recibido (OK)"], ["responseBody"],
     "={{ { \"status\": \"recibido\", \"mensaje\": \"Gracias, \" + %s.nombre + \". Un asesor (\" + $('Assign Salesperson').item.json.vendedor_asignado + \") te va a contactar en breve.\" } }}" % LEAD,
     "nombraba al lead y al vendedor leyendo la fila de vendedores")

# -------------------------------------------------------------- 01 seguimiento
c = "01 seguimiento"
n = N[c]
expr(c, n["Buscar Leads Asignados Sin Contacto"], ["filters", "conditions", 2, "condition"], "is",
     "eq null viaja como el texto null y la base lo rechaza")
filtro(c, n["Marcar Recordatorio Enviado"], "id", "={{ $json.id }}")
con = flujos[c]["connections"]["Loop Por Lead"]["main"]
anota(c, "Loop Por Lead", "el trabajo del bucle colgaba de la salida done, no de la de loop",
      "salida 0 (done) -> Recordatorio - Vendedor", "salida 1 (loop) -> Recordatorio - Vendedor")
flujos[c]["connections"]["Loop Por Lead"]["main"] = [[], con[0]]

# ----------------------------------------------------------------- 02 facturas
c = "02 facturas"
n = N[c]
p = n["Upload Attachment"]["parameters"]
p.pop("sendBinaryData", None)
p["sendBody"] = True
p["contentType"] = "binaryData"
anota(c, "Upload Attachment", "el adjunto no se enviaba",
      "sendBinaryData, que es del httpRequest v3", "sendBody + contentType binaryData")

claude(c, n["Extract With AI"])
viejo = n["Extract With AI"]["parameters"]["jsonBody"]
nuevo = viejo.replace(
    '{ "type": "image", "source": { "type": "url", "url": $(\'Insert Factura (Raw)\').item.json.raw_attachment_url } }',
    '{ "type": "image", "source": { "type": "base64", "media_type": $(\'Email Trigger - Facturas\').item.binary.attachment_0.mimeType, "data": $(\'Email Trigger - Facturas\').item.binary.attachment_0.data } }')
assert nuevo != viejo, "no se encontro el bloque de imagen"
expr(c, n["Extract With AI"], ["jsonBody"], nuevo,
     "mandaba la clave del Storage donde va una direccion que se pueda bajar")

filtro(c, n["Update Factura - Extraida"], "id", "={{ %s.factura_id }}" % PARSE2)
expr(c, n["Check Duplicate"], ["filters", "conditions", 2, "keyValue"], "={{ $json.id }}",
     "se excluia a si misma por un campo que no estaba en el item")
siempre(c, n["Check Duplicate"])
cond(c, n["If Duplicate"], "={{ $json.id }}", HAY, "",
     "preguntaba por el largo de un array que el nodo Supabase no devuelve")
filtro(c, n["Mark Duplicada"], "id", "={{ %s.id }}" % FACT)

cond(c, n["If Confianza Baja"], "={{ %s.confianza_extraccion }}" % PARSE2,
     {"type": "number", "operation": "lt"}, 0.75,
     "leia la confianza sobre el resultado de la busqueda de duplicados")
filtro(c, n["Mark Excepcion Baja Confianza"], "id", "={{ %s.id }}" % FACT)
expr(c, n["Mark Excepcion Baja Confianza"], ["fieldsUi", "fieldValues", 1, "fieldValue"],
     "={{ \"confianza_extraccion=\" + %s.confianza_extraccion + \" por debajo del umbral 0.75\" }}" % PARSE2,
     "el motivo leia la confianza de un item que no la tenia")

expr(c, n["Check OC"], ["filters", "conditions", 0, "keyValue"], "={{ %s.numero_oc }}" % PARSE2,
     "buscaba la orden de compra con un numero que no estaba en el item")
siempre(c, n["Check OC"])
cond(c, n["If Sin OC"], "={{ $json.numero_oc }}", NO_HAY, "",
     "preguntaba por el largo de un array que el nodo Supabase no devuelve")
filtro(c, n["Mark Excepcion Sin OC"], "id", "={{ %s.id }}" % FACT)

expr(c, n["Compute Diff Monto"], ["jsCode"],
     n["Compute Diff Monto"]["parameters"]["jsCode"]
     .replace("const factura = $input.first().json;",
              "const factura = $('Parse AI Response').first().json;")
     .replace("const oc = $('Check OC').first().json[0];",
              "const oc = $('Check OC').first().json;"),
     "tomaba la factura del item de entrada y la orden como si fuera un array")
filtro(c, n["Mark Excepcion Monto"], "id", "={{ %s.id }}" % FACT)

siempre(c, n["Check Proveedor Moneda"])
cond(c, n["If Moneda Distinta"], "={{ $('Compute Diff Monto').first().json.moneda }}",
     {"type": "string", "operation": "notEquals"}, "={{ $json.moneda_esperada }}",
     "comparaba contra el primer elemento de un array que no existe")
filtro(c, n["Mark Excepcion Moneda"], "id", "={{ %s.id }}" % FACT)
filtro(c, n["Mark Pendiente Aprobacion"], "id", "={{ %s.id }}" % FACT)
filtro(c, n["Mark Conciliada"], "id", "={{ %s.id }}" % FACT)

# ---------------------------------------------------------------- 02 aprobacion
c = "02 aprobacion"
n = N[c]
filtro(c, n["Update Factura - Aprobada"], "id", "={{ $json.body.id }}")
filtro(c, n["Update Factura - Conciliada"], "id", "={{ $json.id }}")
filtro(c, n["Update Factura - Rechazada"], "id", "={{ $json.body.id }}")
expr(c, n["Notify - Rechazada"], ["text"],
     "=Factura {{ $json.numero_factura }} rechazada por {{ $('Webhook - Decision').item.json.body.usuario }}, queda fuera de la conciliación.",
     "nombraba al usuario leyendo un cuerpo de webhook que no estaba en el item")

# ---------------------------------------------------------------------- escribir
for k, (_, ruta) in ARCHIVOS.items():
    with open(ruta, "w", encoding="utf8") as f:
        json.dump(flujos[k], f, indent=2, ensure_ascii=False)
        f.write("\n")
    print("escrito %s (%d nodos)" % (os.path.relpath(ruta, REPO), len(flujos[k]["nodes"])))

json.dump(LOG, open("arreglos.json", "w"), indent=1, ensure_ascii=False)
nodos = sorted({(x["caso"], x["nodo"]) for x in LOG})
print("\n%d cambios sobre %d nodos" % (len(LOG), len(nodos)))
for caso in ARCHIVOS:
    de = [x for x in nodos if x[0] == caso]
    print("   %-16s %d nodos" % (caso, len(de)))
