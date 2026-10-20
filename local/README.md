# Entorno local para correr estos workflows

Levanta una base propia, una API REST igual a la de Supabase, un endpoint de Storage y un
buzón de correo, todo en puertos propios y en su propia red de Docker. No toca ningún otro
stack de la máquina.

Las claves JWT que hay en `docker-compose.yml` son locales y de un solo usuario: no abren nada
afuera.

## Levantarlo

    docker compose -f local/docker-compose.yml up -d
    docker network connect pf-net n8n-portfolio

Cargar los esquemas y los catálogos:

    for f in 01-whatsapp-to-supabase/schema.sql 01-whatsapp-to-supabase/seed.sql \
             02-email-invoice-to-supabase/schema.sql 02-email-invoice-to-supabase/seed.sql \
             local/db/99-grants.sql; do
      docker exec -i pf-db psql -v ON_ERROR_STOP=1 -U postgres -d portfolio -q < "$f"
    done

## Las piezas

| contenedor | qué es | puerto en la máquina |
|---|---|---|
| `pf-db` | Postgres 16 con los roles de Supabase (`service_role` con bypassrls) | 55432 |
| `pf-rest` | PostgREST, el mismo motor de API que usa Supabase | solo interno |
| `pf-gw` | traduce `/rest/v1` a PostgREST y resuelve `/storage/v1/object` | 54330 |
| `pf-mail` | GreenMail: SMTP para mandar la factura de muestra, IMAP para que la lea el flujo | 53025 / 53143 |

La puerta existe porque el nodo Supabase de n8n arma la URL como `{host}/rest/v1/<tabla>` y
PostgREST sirve en la raíz.

## Credenciales que espera n8n

- **Supabase**: host `http://pf-gw:8080`, service role la clave JWT del compose.
- **IMAP**: host `pf-mail`, puerto 3143, sin TLS, usuario `facturas@andesfreight.test`.
- **Claude**: header `x-api-key` con una clave de la API de Anthropic.
- **Slack**: credencial creada, nodos desactivados: no hay workspace propio de estos casos.

## Datos de prueba

- `datos/payloads/` : los cuerpos de los webhooks del caso 01, uno por rama.
- `datos/facturas.py` : genera las facturas de muestra del caso 02, una por rama.
  La de confianza baja sale a propósito mal escaneada, para que la poca confianza la produzca
  el material y no un número puesto a mano.

Mandar una factura al buzón:

    python3 - <<'EOF'
    import smtplib
    from email.message import EmailMessage
    m = EmailMessage()
    m["Subject"] = "Factura 0001-00004821 - Combustibles del Litoral SA"
    m["From"] = "facturacion@combustibleslitoral.test"
    m["To"] = "facturas@andesfreight.test"
    m.set_content("Factura por la OC-2026-0441. Documento de ejemplo.")
    m.add_attachment(open("local/datos/facturas/concilia.png", "rb").read(),
                     maintype="image", subtype="png", filename="factura-0001-00004821.png")
    with smtplib.SMTP("127.0.0.1", 53025, timeout=20) as s:
        s.send_message(m)
    EOF

## Bajarlo

    docker compose -f local/docker-compose.yml down        # deja la base
    docker compose -f local/docker-compose.yml down -v     # borra también la base

## Los scripts

| archivo | qué hace |
|---|---|
| `arreglar.py` | aplica los arreglos del 18/10 sobre las copias de `originales/` y escribe los cuatro JSON del repo |
| `importar.py` | pone esos JSON en n8n y les agrega lo que solo vale local: credenciales, Slack desactivado y el host del Storage |
| `comparar.py` | comprueba que el JSON del repo sea el que está publicado y corriendo |
| `capturar.mjs` | captura el lienzo centrado en un nodo, con el cromo de n8n fuera del recorte |
| `verexec.py` | muestra una ejecución nodo por nodo, con items y errores |
| `n8napi.py`, `flatted.py` | el cliente de la API interna de n8n y el lector del formato en que guarda las ejecuciones |

Los tres primeros esperan la sesión del dueño de la instancia local. `n8napi.py` lee el usuario
y la contraseña de un archivo aparte, fuera del repo: si se mueve de máquina hay que apuntarlo
de nuevo en la constante `_CRED`.

`originales/` guarda los cuatro workflows como estaban antes de los arreglos, para poder volver
a aplicar todo desde cero y para poder leer qué cambió.
