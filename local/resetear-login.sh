#!/usr/bin/env bash
# Regenera la credencial de la cuenta de test de n8n (portfolio@local.test) y la
# deja en local/.n8n-cred, que es de donde la lee tramos.mjs.
#
# Por que existe: esa cuenta se creo para capturar los tramos del lienzo y su
# clave quedo guardada en el scratchpad de una sesion, que se borro. No esta
# documentada en ningun lado, asi que la unica salida es regenerarla.
#
# No toca ninguna otra cuenta ni ningun otro n8n: es la instancia local
# n8n-portfolio, que no sirve nada afuera de esta maquina.
#
#   bash local/resetear-login.sh
#
# Deja un log en local/resetear-login.log con lo que paso en cada paso.
set -uo pipefail

CONTENEDOR=n8n-portfolio
CUENTA=portfolio@local.test
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CRED="$AQUI/.n8n-cred"
LOG="$AQUI/resetear-login.log"

: > "$LOG"
paso() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }
morir() { echo "[$(date '+%H:%M:%S')] FALLO: $*" | tee -a "$LOG"; exit 1; }

paso "1/6 el contenedor"
docker inspect "$CONTENEDOR" >/dev/null 2>&1 || morir "no esta corriendo $CONTENEDOR"

paso "2/6 la clave nueva"
PASS=$(python3 -c "import secrets,string; a=string.ascii_letters+string.digits; print(''.join(secrets.choice(a) for _ in range(20)))") \
  || morir "python3 no pudo generar la clave"
[ ${#PASS} -eq 20 ] || morir "la clave salio de ${#PASS} caracteres"

paso "3/6 el hash, con el bcrypt de n8n"
BDIR=$(docker exec "$CONTENEDOR" find /usr/local/lib/node_modules/n8n -maxdepth 6 -type d -name bcryptjs 2>/dev/null | head -1)
[ -n "$BDIR" ] || morir "no encontre bcryptjs adentro del contenedor"
echo "    bcryptjs en $BDIR" >> "$LOG"

HASH=$(printf '%s' "$PASS" | docker exec -i "$CONTENEDOR" node -e '
  let p = "";
  process.stdin.on("data", (d) => { p += d; });
  process.stdin.on("end", () => {
    const bcrypt = require(process.argv[1]);
    process.stdout.write(bcrypt.hashSync(p, 10));
  });
' "$BDIR" 2>>"$LOG")
case "$HASH" in
  '$2a$'*|'$2b$'*|'$2y$'*) echo "    hash de ${#HASH} caracteres" >> "$LOG" ;;
  *) morir "el hash salio con una forma que no es bcrypt (${#HASH} caracteres)" ;;
esac

paso "4/6 a la base"
TMP=$(mktemp /tmp/n8n-reset-XXXX.sqlite)
docker cp "$CONTENEDOR:/home/node/.n8n/database.sqlite" "$TMP" >>"$LOG" 2>&1 \
  || morir "no pude sacar la base del contenedor"
python3 - "$TMP" "$HASH" "$CUENTA" >>"$LOG" 2>&1 <<'PY' || morir "no pude actualizar la cuenta (ver el log)"
import sqlite3, sys
base, hash_, cuenta = sys.argv[1], sys.argv[2], sys.argv[3]
c = sqlite3.connect(base)
n = c.execute("update user set password=? where email=?", (hash_, cuenta)).rowcount
c.commit(); c.close()
if n != 1:
    raise SystemExit(f"se esperaba una cuenta y se actualizaron {n}")
print("    cuenta actualizada")
PY
docker cp "$TMP" "$CONTENEDOR:/home/node/.n8n/database.sqlite" >>"$LOG" 2>&1 \
  || morir "no pude devolver la base al contenedor"
rm -f "$TMP"

paso "5/6 reiniciar n8n"
docker restart "$CONTENEDOR" >>"$LOG" 2>&1 || morir "no pude reiniciar $CONTENEDOR"
for i in $(seq 1 30); do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://localhost:5678/signin || true)
  [ "$code" = "200" ] && break
  sleep 2
done
[ "${code:-}" = "200" ] || morir "n8n no volvio a contestar despues de reiniciar"
echo "    n8n contesta de nuevo" >> "$LOG"

paso "6/6 la credencial al archivo del proyecto"
umask 077
printf 'email: %s\npass: %s\n' "$CUENTA" "$PASS" > "$CRED"
[ -s "$CRED" ] || morir "no pude escribir $CRED"

paso "listo. La credencial quedo en local/.n8n-cred (gitignoreada)."
