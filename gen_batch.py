"""
gen_batch.py - Genera contenido LLM + XLSX para una lista de LPs (MCR + VJM).

Lee batch_lps.json con la seleccion de LPs y para cada uno:
  1. Obtiene metadata de BD (ciudad, estado, dominio, etc)
  2. Genera contenido por bloques via LLM (lm_client)
  3. Construye XLSX final usando builder_mcr o builder_vjm

Output:
  - batch_progress.json: estado de cada LP
  - XLSX en RESULTADOS MCR/VJS/CARGUES DE CONTENIDO/
"""
import json
import sys
import time
import sqlite3
import logging
from pathlib import Path

import builder_mcr
import builder_vjm
from lm_client import LMClient

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("batch")

ROOT = Path(__file__).parent
PROGRESS_PATH = ROOT / "batch_progress.json"
LPS_PATH = ROOT / "batch_lps.json"


# ══════════════════════════════════════════════════════════════════════
# UTILIDADES
# ══════════════════════════════════════════════════════════════════════

ESTADOS = {  # ciudad -> (estado, abrev)
    "Memphis": ("Tennessee", "TN"),
    "Nashville": ("Tennessee", "TN"),
    "Charlotte": ("North Carolina", "NC"),
    "Atlanta": ("Georgia", "GA"),
    "Tampa": ("Florida", "FL"),
    "Miami": ("Florida", "FL"),
    "Orlando": ("Florida", "FL"),
    "Las Vegas": ("Nevada", "NV"),
    "Austin": ("Texas", "TX"),
    "Boston": ("Massachusetts", "MA"),
    "Houston": ("Texas", "TX"),
    "Dallas": ("Texas", "TX"),
    "New York": ("New York", "NY"),
    "Los Angeles": ("California", "CA"),
    "San Francisco": ("California", "CA"),
}


def lp_metadata(db, lp_id):
    """Devuelve dict con ciudad, estado, abrev, agencia, etc."""
    row = db.execute("SELECT * FROM landing_pages WHERE id=?", (lp_id,)).fetchone()
    if not row:
        raise ValueError(f"LP {lp_id} no encontrada")
    lp = dict(row)
    sentinelas = {"no es localidad", "no es agencia", "no es tipo de autos",
                  "no es ciudad", "no es oferta"}

    def real(v):
        return v if (v and v.strip().lower() not in sentinelas) else ""

    ciudad = real(lp["ciudad"])
    localidad = real(lp["localidad"])
    agencia = real(lp["agencia"])
    car_cat = real(lp["car_category"])

    estado, abrev = ESTADOS.get(ciudad, (lp.get("estado", ""), ""))
    if not estado and ciudad:
        estado = "Estados Unidos"
        abrev = "USA"

    return {
        "lp_id": lp_id,
        "tipo_lp_bd": lp["tipo_lp"],
        "ciudad": ciudad,
        "localidad": localidad,
        "agencia": agencia,
        "car_category": car_cat,
        "estado": estado,
        "abrev": abrev,
        "dominio": lp.get("dominio", ""),
    }


# ══════════════════════════════════════════════════════════════════════
# GENERADORES DE CONTENIDO
# ══════════════════════════════════════════════════════════════════════

def generate_mcr_content(client, meta, tipo):
    """Genera contenido MCR completo (8 bloques) para un LP."""
    ciudad = meta["ciudad"] or meta["localidad"] or "USA"
    estado = meta["estado"] or "USA"
    abrev = meta["abrev"] or "US"
    agencia = meta["agencia"]
    car_cat = meta["car_category"]
    localidad = meta["localidad"]
    precio = "9"

    # Nombre principal para LP
    if tipo == "agencia" and agencia:
        nombre = f"{agencia} {ciudad}" if ciudad else agencia
    elif tipo == "tipo_auto" and car_cat:
        nombre = f"{car_cat} {ciudad}" if ciudad else car_cat
    elif tipo == "localidad":
        nombre = localidad or ciudad
    else:
        nombre = ciudad

    bloques = {}

    # quicksearch
    bloques["quicksearch"] = client.generate_quicksearch(nombre, estado)

    # fleet
    bloques["fleet"] = client.generate_fleet(nombre, estado)

    # questions: header + preguntas estandar + answers
    qh = client.generate_questions_header(ciudad, estado)
    qa = client.generate_faq_answers(ciudad, estado, abrev,
                                     precio_dia=precio,
                                     precio_semana=str(int(precio)*7),
                                     agencias_precios=[("Alamo","9"),("Dollar","10"),("Avis","11")])
    ub = f"{ciudad}, {estado}" if estado else ciudad
    qq = {
        "q_1": f"¿Cuánto cuesta rentar un auto en {ciudad}?",
        "q_2": f"¿Qué se necesita para rentar un carro en {ub}?",
        "q_3": f"¿Cuál es la agencia más barata para alquilar autos en {ciudad}?",
        "q_4": f"¿Cuánto cuesta el alquiler de un auto por una semana en {ciudad}?",
    }
    bloques["questions"] = {**qh, **qq, **qa}

    # reviews
    bloques["reviews"] = client.generate_reviews(ciudad, estado)

    # rentcompanies
    bloques["rentcompanies"] = client.generate_rentcompanies(ciudad, estado)

    # fleetcarrusel (skip si tipo_auto)
    skip = car_cat if tipo == "tipo_auto" else ""
    bloques["fleetcarrusel"] = client.generate_fleetcarrusel(
        ciudad, estado, estado_abrev=abrev, skip_type=skip)

    # locationscarrusel
    bloques["locationscarrusel"] = client.generate_locationscarrusel(
        ciudad, estado, tipo_lp=tipo)

    # rentacar
    bloques["rentacar"] = client.generate_rentacar(
        nombre, estado, tipo_lp=tipo,
        agencia=agencia, tipo_auto=car_cat, localidad=localidad)

    return bloques


def translate_content(client, bloques):
    """Traduce todos los bloques de ES a EN y PT.

    Traduce bloque por bloque para eficiencia (1 llamada por bloque por idioma).
    Retorna (content_en, content_pt).
    """
    content_en = {}
    content_pt = {}

    for bloque_name, fields in bloques.items():
        if not fields or not isinstance(fields, dict):
            continue
        # Filtrar campos vacios y muy cortos (titulos de 1-2 palabras se traducen tambien)
        translatable = {k: v for k, v in fields.items()
                        if v and isinstance(v, str) and len(v.strip()) > 0}
        if not translatable:
            continue

        try:
            en_fields = client.translate_fields(translatable, "en")
            content_en[bloque_name] = en_fields
        except Exception as e:
            log.warning("Traduccion EN fallo para %s: %s", bloque_name, e)
            content_en[bloque_name] = {}

        try:
            pt_fields = client.translate_fields(translatable, "pt")
            content_pt[bloque_name] = pt_fields
        except Exception as e:
            log.warning("Traduccion PT fallo para %s: %s", bloque_name, e)
            content_pt[bloque_name] = {}

    return content_en, content_pt


def generate_vjm_content(client, meta, tipo):
    """Genera contenido VJM (6 bloques) para un LP."""
    ciudad = meta["ciudad"] or meta["localidad"] or "USA"
    estado = meta["estado"] or "USA"
    abrev = meta["abrev"] or "US"
    agencia = meta["agencia"]
    car_cat = meta["car_category"]
    precio = "9"

    bloques = {}

    bloques["quicksearch"] = client.generate_vjm_quicksearch(ciudad, estado)
    bloques["sectionCars"] = client.generate_vjm_sectioncars(ciudad, estado)
    bloques["agencies"] = client.generate_vjm_agencies(ciudad, estado)

    qh = client.generate_vjm_rentalcarfaqs_header(ciudad, estado)
    qq = client.generate_vjm_faq_questions(ciudad, estado)
    qa = client.generate_vjm_faq_answers(ciudad, estado, abrev, precio_dia=precio)
    bloques["rentalCarFaqs"] = {**qh, **qq, **qa}

    bloques["favoriteCities"] = client.generate_vjm_favoritecities(ciudad, estado)
    bloques["carRental"] = client.generate_vjm_carrental(
        ciudad, estado, estado_abrev=abrev)

    return bloques


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════

def load_progress():
    if PROGRESS_PATH.exists():
        with open(PROGRESS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_progress(progress):
    with open(PROGRESS_PATH, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def run_batch():
    with open(LPS_PATH, "r", encoding="utf-8") as f:
        lps = json.load(f)

    progress = load_progress()
    db = sqlite3.connect("bd_urls.db")
    db.row_factory = sqlite3.Row

    client_mcr = LMClient(brand="mcr")
    client_vjm = LMClient(brand="vjm")

    total = len(lps["MCR"]) + len(lps["VJM"])
    done = 0
    t_global = time.time()

    log.info("=" * 70)
    log.info("BATCH START: %d MCR + %d VJM = %d total LPs",
             len(lps["MCR"]), len(lps["VJM"]), total)
    log.info("=" * 70)

    # ── MCR ──
    for entry in lps["MCR"]:
        lp_id = entry["lp_id"]
        tipo = entry["tipo"]
        label = entry["label"]
        key = f"MCR_{lp_id}"

        if progress.get(key, {}).get("status") == "done":
            log.info("[%d/%d] SKIP (ya hecho) MCR %d %s", done+1, total, lp_id, label)
            done += 1
            continue

        log.info("[%d/%d] MCR %d (%s) %s ...", done+1, total, lp_id, tipo, label)
        t0 = time.time()
        try:
            meta = lp_metadata(db, lp_id)
            bloques = generate_mcr_content(client_mcr, meta, tipo)
            # Traducir a EN y PT
            log.info("[%d/%d] MCR %d traduciendo EN+PT...", done+1, total, lp_id)
            content_en, content_pt = translate_content(client_mcr, bloques)
            path = builder_mcr.build_single(
                db, lp_id, content=bloques,
                content_en=content_en, content_pt=content_pt,
            )
            elapsed = round(time.time() - t0, 1)
            progress[key] = {
                "status": "done",
                "tipo": tipo,
                "label": label,
                "elapsed_s": elapsed,
                "path": path,
            }
            log.info("[%d/%d] MCR %d OK en %.1fs -> %s",
                     done+1, total, lp_id, elapsed, Path(path).name)
        except Exception as e:
            elapsed = round(time.time() - t0, 1)
            log.error("[%d/%d] MCR %d FAIL en %.1fs: %s", done+1, total, lp_id, elapsed, e)
            progress[key] = {"status": "error", "error": str(e), "elapsed_s": elapsed}
        save_progress(progress)
        done += 1

    # ── VJM ──
    for entry in lps["VJM"]:
        lp_id = entry["lp_id"]
        tipo = entry["tipo"]
        label = entry["label"]
        key = f"VJM_{lp_id}"

        if progress.get(key, {}).get("status") == "done":
            log.info("[%d/%d] SKIP (ya hecho) VJM %d %s", done+1, total, lp_id, label)
            done += 1
            continue

        log.info("[%d/%d] VJM %d (%s) %s ...", done+1, total, lp_id, tipo, label)
        t0 = time.time()
        try:
            meta = lp_metadata(db, lp_id)
            bloques = generate_vjm_content(client_vjm, meta, tipo)
            # Traducir a EN y PT
            log.info("[%d/%d] VJM %d traduciendo EN+PT...", done+1, total, lp_id)
            content_en, content_pt = translate_content(client_vjm, bloques)
            path = builder_vjm.build_single(
                db, lp_id, content=bloques,
                content_en=content_en, content_pt=content_pt,
            )
            elapsed = round(time.time() - t0, 1)
            progress[key] = {
                "status": "done",
                "tipo": tipo,
                "label": label,
                "elapsed_s": elapsed,
                "path": path,
            }
            log.info("[%d/%d] VJM %d OK en %.1fs -> %s",
                     done+1, total, lp_id, elapsed, Path(path).name)
        except Exception as e:
            elapsed = round(time.time() - t0, 1)
            log.error("[%d/%d] VJM %d FAIL en %.1fs: %s", done+1, total, lp_id, elapsed, e)
            progress[key] = {"status": "error", "error": str(e), "elapsed_s": elapsed}
        save_progress(progress)
        done += 1

    db.close()
    elapsed_total = round((time.time() - t_global) / 60, 1)
    ok = sum(1 for v in progress.values() if v.get("status") == "done")
    err = sum(1 for v in progress.values() if v.get("status") == "error")
    log.info("=" * 70)
    log.info("BATCH FIN: %d OK / %d errores en %.1f min", ok, err, elapsed_total)
    log.info("=" * 70)


if __name__ == "__main__":
    run_batch()
