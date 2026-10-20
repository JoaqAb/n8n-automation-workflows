"""Genera las facturas de muestra que el caso 02 usa para correr.

Negocio y datos ficticios. Cada archivo apunta a una rama distinta del flujo:
el camino que concilia y los cuatro controles que fallan. La de confianza baja
sale a proposito degradada, para que la extraccion con IA devuelva poca
confianza por el material y no por un numero puesto a mano.

    python3 facturas.py            escribe los PNG en ./facturas/
"""
import os
from PIL import Image, ImageDraw, ImageFont

SALIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "facturas")
F = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FM = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"

# archivo, proveedor, numero, oc, moneda, lineas, degradada.
# Cada linea es (descripcion, cantidad, unidad, precio unitario). El total de la factura es la
# suma de cantidad por precio: una factura que no cierra hace dudar a la extraccion, y con
# razon, asi que las que tienen que salir confiadas cierran.
CASOS = [
    ("concilia", "Combustibles del Litoral SA", "0001-00004821", "OC-2026-0441", "ARS",
     [("Gasoil grado 2, carga de flota", 4000, "l", 46.25)], False),
    ("monto-distinto", "Repuestos Andinos SRL", "0002-00000517", "OC-2026-0442", "ARS",
     [("Kit de frenos remolque", 2, "u", 24800.0), ("Mangueras de aire", 8, "u", 2850.0)], False),
    ("sin-orden-de-compra", "Repuestos Andinos SRL", "0002-00000533", "OC-2026-9144", "ARS",
     [("Filtros de aire para motor", 10, "u", 2250.0), ("Correas de distribucion", 3, "u", 3000.0)], False),
    ("moneda-distinta", "Repuestos Andinos SRL", "0002-00000540", "OC-2026-0442", "USD",
     [("Repuestos de refrigeracion, lote completo", 1, "lote", 62000.0)], False),
    ("confianza-baja", "Repuestos Andinos SRL", "0002-00000551", "OC-2026-0442", "ARS",
     [("Servicio de taller", 1, "u", 61800.0)], True),
]


def fuente(ruta, tam):
    try:
        return ImageFont.truetype(ruta, tam)
    except OSError:
        return ImageFont.load_default()


def dibujar(nombre, proveedor, numero, oc, moneda, lineas, degradada):
    monto = sum(c * p for _, c, _, p in lineas)
    an, al = 1240, 1754  # A4 a 150 dpi
    im = Image.new("RGB", (an, al), "white")
    d = ImageDraw.Draw(im)
    tit, neg, txt, mono = fuente(FB, 46), fuente(FB, 26), fuente(F, 24), fuente(FM, 24)

    d.text((70, 80), proveedor, font=tit, fill="black")
    d.text((70, 140), "CUIT 30-71455820-4   Ruta 9 km 1284, Tucuman", font=txt, fill=(70, 70, 70))
    d.line((70, 190, an - 70, 190), fill="black", width=3)

    d.text((70, 220), "FACTURA B", font=neg, fill="black")
    d.text((70, 262), "Numero: " + numero, font=mono, fill="black")
    d.text((70, 300), "Fecha de emision: 14/10/2026", font=mono, fill="black")
    d.text((70, 338), "Orden de compra: " + oc, font=mono, fill="black")
    d.text((70, 376), "Cliente: Andes Freight SA", font=mono, fill="black")
    d.text((70, 414), "Condicion de venta: cuenta corriente 30 dias", font=mono, fill="black")

    y = 500
    d.line((70, y - 16, an - 70, y - 16), fill=(150, 150, 150), width=2)
    d.text((70, y), "Detalle", font=neg, fill="black")
    d.text((610, y), "Cant.", font=neg, fill="black")
    d.text((760, y), "Precio unit.", font=neg, fill="black")
    d.text((an - 70 - d.textlength("Importe", font=neg), y), "Importe", font=neg, fill="black")
    y += 50
    for desc, cant, unidad, precio in lineas:
        d.text((70, y), desc, font=txt, fill="black")
        d.text((610, y), "%g %s" % (cant, unidad), font=txt, fill="black")
        d.text((760, y), "%0.2f" % precio, font=mono, fill="black")
        imp = "{:,.2f}".format(cant * precio).replace(",", ".")
        d.text((an - 70 - d.textlength(imp, font=mono), y), imp, font=mono, fill="black")
        y += 44
    d.line((70, y + 10, an - 70, y + 10), fill=(150, 150, 150), width=2)

    total = "%s %s" % (moneda, "{:,.2f}".format(monto).replace(",", "."))
    ftot = fuente(FB, 30)
    d.text((700, y + 50), "TOTAL", font=neg, fill="black")
    d.text((an - 70 - d.textlength(total, font=ftot), y + 50), total, font=ftot, fill="black")

    d.text((70, al - 140), "Documento de ejemplo. Negocio y datos ficticios.",
           font=fuente(F, 20), fill=(120, 120, 120))

    if degradada:
        # Factura mal escaneada: chica, torcida, movida y lavada. Es el material el que baja la
        # confianza de la extraccion, no un numero puesto a mano. Medido el 18/10/2026: a un
        # cuarto de tamano el modelo todavia contestaba 0.75, o sea que no dudaba de un escaneo
        # que ya leia mal. Con esto duda.
        from PIL import ImageFilter
        im = im.rotate(-5.5, expand=True, fillcolor="white")
        im = im.resize((im.width // 5, im.height // 5), Image.BILINEAR)
        im = im.filter(ImageFilter.GaussianBlur(0.6))
        im = im.point(lambda v: int(200 + v * 0.21))

    os.makedirs(SALIDA, exist_ok=True)
    ruta = os.path.join(SALIDA, "%s.png" % nombre)
    im.save(ruta)
    print("%-22s %s  %4dx%-4d  %d bytes" % (nombre, numero, im.width, im.height, os.path.getsize(ruta)))
    return ruta


if __name__ == "__main__":
    for c in CASOS:
        dibujar(*c)
