"""Puerta de entrada local que imita las dos rutas de Supabase que usan los workflows.

Por que existe: el nodo Supabase de n8n arma la URL como {host}/rest/v1/<tabla>, y
PostgREST sirve en la raiz. Esta puerta traduce ese prefijo, y de paso resuelve el
endpoint de Storage que usa el nodo Upload Attachment del caso 02.

    /rest/v1/<...>                         -> PostgREST
    /storage/v1/object/<bucket>/<path>     -> guarda el archivo (POST o PUT)
    /storage/v1/object/public/<b>/<path>   -> devuelve el archivo (GET)

No hay autenticacion propia: los headers apikey y Authorization viajan tal cual a
PostgREST, que valida el JWT. Es un entorno local de un solo usuario.
"""

import json
import os
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

REST = os.environ.get("REST_UPSTREAM", "http://pf-rest:3000")
DATA = os.environ.get("STORAGE_DIR", "/data")
PORT = int(os.environ.get("PORT", "8080"))
PASS_THROUGH = ("authorization", "apikey", "prefer", "content-type", "accept", "range")
TIPOS = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
         ".pdf": "application/pdf", ".txt": "text/plain"}


class Puerta(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "pf-gw/1"

    def log_message(self, fmt, *args):
        print("%s %s" % (self.command, self.path), flush=True)

    # --- helpers -----------------------------------------------------------
    def _cuerpo(self):
        largo = int(self.headers.get("content-length") or 0)
        return self.rfile.read(largo) if largo else None

    def _responder(self, codigo, cuerpo=b"", tipo="application/json"):
        if isinstance(cuerpo, str):
            cuerpo = cuerpo.encode()
        self.send_response(codigo)
        self.send_header("content-type", tipo)
        self.send_header("content-length", str(len(cuerpo)))
        self.end_headers()
        if cuerpo:
            self.wfile.write(cuerpo)

    def _ruta_archivo(self, resto):
        partes = [p for p in resto.split("/") if p and p != ".."]
        return os.path.join(DATA, *partes), "/".join(partes)

    # --- PostgREST ---------------------------------------------------------
    def _proxy(self, camino):
        url = REST + camino
        pedido = Request(url, data=self._cuerpo(), method=self.command)
        for h in PASS_THROUGH:
            if self.headers.get(h):
                pedido.add_header(h, self.headers[h])
        try:
            with urlopen(pedido, timeout=30) as r:
                datos, codigo, tipo = r.read(), r.status, r.headers.get("content-type", "application/json")
        except HTTPError as e:
            datos, codigo, tipo = e.read(), e.code, e.headers.get("content-type", "application/json")
        except Exception as e:  # upstream caido
            datos, codigo, tipo = json.dumps({"message": str(e)}).encode(), 502, "application/json"
        self._responder(codigo, datos, tipo)

    # --- Storage -----------------------------------------------------------
    def _guardar(self, resto):
        destino, clave = self._ruta_archivo(resto)
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        cuerpo = self._cuerpo() or b""
        with open(destino, "wb") as f:
            f.write(cuerpo)
        print("guardado %s (%d bytes)" % (clave, len(cuerpo)), flush=True)
        self._responder(200, json.dumps({"Key": clave, "Id": str(uuid.uuid4())}))

    def _servir(self, resto):
        origen, _ = self._ruta_archivo(resto)
        if not os.path.isfile(origen):
            return self._responder(404, json.dumps({"message": "not found"}))
        ext = os.path.splitext(origen)[1].lower()
        with open(origen, "rb") as f:
            self._responder(200, f.read(), TIPOS.get(ext, "application/octet-stream"))

    # --- ruteo -------------------------------------------------------------
    def _ruteo(self):
        camino = urlsplit(self.path).path
        cola = self.path[len("/rest/v1"):] if camino.startswith("/rest/v1") else None
        if cola is not None:
            return self._proxy(cola or "/")
        if camino.startswith("/storage/v1/object/public/"):
            if self.command == "GET":
                return self._servir(camino[len("/storage/v1/object/public/"):])
            return self._responder(405, json.dumps({"message": "method not allowed"}))
        if camino.startswith("/storage/v1/object/"):
            resto = camino[len("/storage/v1/object/"):]
            if self.command in ("POST", "PUT"):
                return self._guardar(resto)
            if self.command == "GET":
                return self._servir(resto)
            return self._responder(405, json.dumps({"message": "method not allowed"}))
        if camino == "/salud":
            return self._responder(200, json.dumps({"status": "ok"}))
        self._responder(404, json.dumps({"message": "sin ruta: " + camino}))

    do_GET = do_POST = do_PATCH = do_PUT = do_DELETE = do_HEAD = _ruteo


if __name__ == "__main__":
    os.makedirs(DATA, exist_ok=True)
    print("puerta local en :%d -> %s" % (PORT, REST), flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Puerta).serve_forever()
