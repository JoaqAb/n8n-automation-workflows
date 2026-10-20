"""Cliente minimo de la API interna de n8n con la sesion del dueno."""
import json, re, urllib.request, urllib.error, http.cookiejar

BASE = "http://localhost:5678"
_CRED = "/tmp/claude-1000/-home-joaquin-proyectos/93f977d9-f8dc-41c2-967b-ba835c581639/scratchpad/n8n-local.txt"
_jar = http.cookiejar.CookieJar()
_op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_jar))


def pedir(metodo, ruta, cuerpo=None, crudo=False):
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(BASE + ruta, data=datos, method=metodo,
                                 headers={"content-type": "application/json",
                                          "browser-id": "portfolio-cli"})
    try:
        with _op.open(req, timeout=120) as r:
            txt = r.read()
            return r.status, (txt if crudo else json.loads(txt or b"{}"))
    except urllib.error.HTTPError as e:
        txt = e.read()
        try:
            return e.code, json.loads(txt or b"{}")
        except Exception:
            return e.code, {"raw": txt[:500].decode("utf8", "replace")}


def entrar():
    t = open(_CRED).read()
    email = re.search(r"email:\s*(\S+)", t).group(1)
    pwd = re.search(r"pass:\s*(\S+)", t).group(1)
    c, _ = pedir("POST", "/rest/login", {"emailOrLdapLoginId": email, "password": pwd})
    assert c == 200, c
    return c


def flujo(wid):
    return pedir("GET", "/rest/workflows/" + wid)[1]["data"]


def guardar(wid, w):
    campos = {k: w[k] for k in ("name", "nodes", "connections", "settings") if k in w}
    campos["versionId"] = w.get("versionId")
    return pedir("PATCH", "/rest/workflows/" + wid, campos)
