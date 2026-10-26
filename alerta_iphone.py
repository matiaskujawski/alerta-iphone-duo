#!/usr/bin/env python3
"""
Alerta de stock: iPhone Duo 256GB Star White - retiro en Apple Aventura (Miami).

Consulta cada ~60 s el mismo servicio que usa apple.com cuando elegís
"Pick up" y te manda una notificación push al celular (vía ntfy) apenas
aparece disponible. No usa IA ni gasta tokens: es Python puro, sin
librerías externas.

Uso:
  1. Instalá la app "ntfy" en el celular (iOS / Android, gratis) y
     suscribite al tema que pongas en NTFY_TOPIC (inventá uno raro).
  2. python3 alerta_iphone.py           -> corre para siempre
     python3 alerta_iphone.py --test    -> manda una notificación de prueba
                                           y hace una sola consulta
  Cortalo con Ctrl+C.
"""

import json
import os
import random
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime

# ---------------- CONFIGURACIÓN ----------------
# (En GitHub Actions estos valores pueden venir de variables de entorno)
PART_NUMBER = os.environ.get("PART_NUMBER", "MK1E4LL/A")  # iPhone Duo 256GB Star White (EE.UU.)
ZIP_CODE = os.environ.get("ZIP_CODE", "33180")             # Código postal de Aventura, FL
STORE_NAME_CONTAINS = os.environ.get("STORE_NAME", "Aventura")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC") or "iphone-duo-mati-CAMBIAME-123"
INTERVALO_SEG = 60             # cada cuánto consulta (no bajes de 30)
REPETIR_ALERTA_SEG = 300       # mientras siga habiendo stock, re-avisa cada 5 min
# Si está definido, el script termina solo después de estos segundos
# (GitHub corta los trabajos a las 6 h; el workflow lo vuelve a lanzar).
MAX_RUNTIME_SEG = int(os.environ.get("MAX_RUNTIME_SEG", "0"))
# ------------------------------------------------

URL = "https://www.apple.com/shop/fulfillment-messages?" + urllib.parse.urlencode({
    "fae": "true",
    "pl": "true",
    "mts.0": "regular",
    "parts.0": PART_NUMBER,
    "location": ZIP_CODE,
})
LINK_COMPRA = "https://www.apple.com/shop/buy-iphone/iphone-duo"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": LINK_COMPRA,
}


def log(msg):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def notificar(titulo, mensaje, prioridad="urgent"):
    req = urllib.request.Request(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=mensaje.encode("utf-8"),
        headers={
            "Title": titulo.encode("utf-8"),
            "Priority": prioridad,
            "Tags": "iphone,rotating_light",
            "Click": LINK_COMPRA,
        },
    )
    try:
        urllib.request.urlopen(req, timeout=15).read()
    except Exception as e:
        log(f"No pude mandar la notificación: {e}")
    # Pitido en la compu también
    print("\a", end="", flush=True)


def consultar():
    """Devuelve (disponible: bool | None, detalle: str)."""
    req = urllib.request.Request(URL, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read().decode("utf-8"))

    stores = data.get("body", {}).get("content", {}).get("pickupMessage", {}).get("stores", [])
    if not stores:
        return None, "Apple no devolvió tiendas (¿número de parte mal?)"

    for s in stores:
        nombre = s.get("storeName", "")
        if STORE_NAME_CONTAINS.lower() not in nombre.lower():
            continue
        parte = s.get("partsAvailability", {}).get(PART_NUMBER, {})
        estado = parte.get("pickupDisplay", "?")
        cuando = parte.get("pickupSearchQuote") or parte.get("storePickupQuote") or ""
        return estado == "available", f"{nombre}: {estado} {cuando}".strip()

    cercanas = ", ".join(s.get("storeName", "?") for s in stores[:5])
    return None, f"No encontré '{STORE_NAME_CONTAINS}' entre: {cercanas}"


def main():
    modo_test = "--test" in sys.argv
    log(f"Vigilando {PART_NUMBER} en '{STORE_NAME_CONTAINS}' (ZIP {ZIP_CODE})")

    if modo_test:
        notificar("Prueba OK", "Si ves esto, las alertas funcionan.", "default")
        log("Notificación de prueba enviada.")

    ultima_alerta = 0.0
    errores_seguidos = 0
    inicio = time.time()

    while True:
        if MAX_RUNTIME_SEG and time.time() - inicio > MAX_RUNTIME_SEG:
            log("Tiempo máximo alcanzado, termino (el próximo turno sigue).")
            break
        try:
            disponible, detalle = consultar()
            errores_seguidos = 0
            log(detalle)

            if disponible:
                ahora = time.time()
                if ahora - ultima_alerta >= REPETIR_ALERTA_SEG:
                    notificar("¡HAY STOCK en Aventura!",
                              f"iPhone Duo 256GB blanco disponible para retiro.\n{detalle}\nTocá para comprar.")
                    ultima_alerta = ahora
            elif disponible is False:
                ultima_alerta = 0.0
        except Exception as e:
            errores_seguidos += 1
            log(f"Error consultando Apple: {e}")
            if errores_seguidos == 10:
                notificar("Alerta iPhone: problema",
                          f"10 errores seguidos consultando Apple. Último: {e}", "default")

        if modo_test:
            break
        # Espera con algo de azar para no parecer un robot; más larga si hay errores
        espera = INTERVALO_SEG * (1 + min(errores_seguidos, 5)) + random.uniform(0, 15)
        time.sleep(espera)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Cortado.")
