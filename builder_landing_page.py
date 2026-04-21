"""
builder_landing_page.py — Construye la hoja LandingPage del XLSX de cargue.

Lee datos de bd_urls.db y genera la fila correspondiente en la hoja LandingPage
para MCR y VJM. Diseñado para cargues masivos (~6,000 LPs).

Columnas MCR (A-M):
  A: Nombre del sitio
  B: Url LandingPage (path ES)
  C: HighPrice (fijo 186.02)
  D: LowPrice (fijo 9)
  E: Titulo LP (Ingles)
  F: Meta titulo (Ingles)
  G: Meta descripcion (Ingles)
  H: Titulo Lp (Espanol)
  I: Meta titulo (espanol)
  J: Meta descripcion (Espanol)
  K: Titulo Lp (Portugues)
  L: Meta titulo (Portugues)
  M: Meta descripcion (Portugues)
"""
import sqlite3
import os
import re
import logging

log = logging.getLogger("builder_lp")

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(ROOT, "bd_urls.db")

# ── Precios fijos ──────────────────────────────────────────────────────
MCR_HIGH_PRICE = 186.02
MCR_LOW_PRICE = 9

# ── Mapeo dominios MCR con ciudad embebida ─────────────────────────────
# El "Nombre del sitio" se construye desde el dominio.
MCR_DOMAIN_CITY = {
    "milescarrentalnewyork.com": "New York",
    "milescarrentaltampa.com": "Tampa",
    "milescarrentalhouston.com": "Houston",
    "milescarrentalpalmbeach.com": "Palm Beach",
    "milescarrentallosangeles.com": "Los Angeles",
    "milescarrentallasvegas.com": "Las Vegas",
    "milescarrentalatlanta.com": "Atlanta",
    "milescarrentalsanfrancisco.com": "San Francisco",
    "milescarrentalsandiego.com": "San Diego",
    "milescarrentaldallas.com": "Dallas",
    "milescarrentalfortlauderdale.com": "Fort Lauderdale",
    "milescarrentalorlando.com": "Orlando",
    "milescarrentalmiami.com": "Miami",
}

# ── Dominios MCR por pais (no incluyen ciudad) ─────────────────────────
# milescarrental.com.es es el UNICO que usa "coches" como KW principal.
MCR_DOMAIN_COUNTRY_KW = {
    "milescarrental.com.es": "coches",
}

MARCA = {
    "MCR": "Miles Car Rental",
    "VJM": "Viajemos",
}


def _extraer_host(dominio: str) -> str:
    """Limpia el dominio: https://www.milescarrentalatlanta.com/ -> milescarrentalatlanta.com"""
    host = re.sub(r"^https?://", "", dominio or "")
    host = re.sub(r"^www\.", "", host)
    return host.rstrip("/")


def get_site_city(dominio: str) -> str:
    """Retorna la ciudad embebida en el dominio (si aplica). '' si es generico."""
    host = _extraer_host(dominio)
    return MCR_DOMAIN_CITY.get(host, "")


def get_kw_autos(dominio: str, lang: str) -> str:
    """Palabra clave principal para 'autos' segun dominio e idioma.

    Regla: 'coches' SOLO en milescarrental.com.es (idioma ES).
    Default: ES='autos', EN='cars', PT='carros'.
    """
    host = _extraer_host(dominio)
    if lang == "ES" and MCR_DOMAIN_COUNTRY_KW.get(host) == "coches":
        return "coches"
    if lang == "EN":
        return "cars"
    if lang == "PT":
        return "carros"
    return "autos"


def _get_db(db_path: str = DB_PATH) -> sqlite3.Connection:
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    return db


def construir_nombre_sitio(lp: dict) -> str:
    """Construye col A: 'Nombre del sitio' = nombre del NEGOCIO segun el dominio.

    Ejemplos:
      milescarrentalatlanta.com -> 'Miles Car Rental Atlanta'
      milescarrental.com        -> 'Miles Car Rental'
      milescarrental.com.es     -> 'Miles Car Rental'
    No depende de la LP individual (agencia/tipo_auto/etc), solo del dominio.
    """
    marca = MARCA.get(lp["proyecto"], lp["proyecto"])
    dominio = lp.get("dominio", "")
    site_city = get_site_city(dominio)
    if site_city:
        return f"{marca} {site_city}"
    return marca


def obtener_url_es(db: sqlite3.Connection, lp_id: int) -> str:
    """Obtiene el url_path del idioma ES para una LP."""
    row = db.execute(
        "SELECT url_path FROM urls WHERE lp_id = ? AND idioma = 'ES' LIMIT 1",
        (lp_id,)
    ).fetchone()
    return row["url_path"] if row else ""


def obtener_urls_trinomio(db: sqlite3.Connection, lp_id: int) -> dict:
    """Retorna {idioma: {url_path, h1, meta_title, meta_description}} para una LP."""
    rows = db.execute(
        "SELECT idioma, url_path, h1, meta_title, meta_description "
        "FROM urls WHERE lp_id = ? ORDER BY orden_trinomio",
        (lp_id,)
    ).fetchall()
    return {r["idioma"]: dict(r) for r in rows}


def generar_meta_titulo(ubicacion: str, tipo_lp: str, lang: str,
                        dominio: str = "", precio: int = MCR_LOW_PRICE,
                        marca: str = "MCR") -> str:
    """Meta titulo al estilo Miles/Viajemos (pattern Miami/Orlando):
      ES: 'Alquiler de Autos {ubicacion} - Mejores Tarifas USD ${precio}/d'
      EN: 'Rent a Car {ubicacion} - Best Rates USD ${precio}/d'
      PT: 'Aluguel de Carros {ubicacion} - Melhores Tarifas USD ${precio}/d'

    Para Spain (.com.es) en ES: 'Alquiler de Coches ...'
    """
    kw = get_kw_autos(dominio, lang)
    if lang == "EN":
        return f"Rent a Car {ubicacion} - Best Rates USD ${precio}/d"
    if lang == "PT":
        return f"Aluguel de {kw.capitalize()} {ubicacion} - Melhores Tarifas USD ${precio}/d"
    # ES (default)
    return f"Alquiler de {kw.capitalize()} {ubicacion} - Mejores Tarifas USD ${precio}/d"


def generar_meta_descripcion(ubicacion: str, tipo_lp: str, lang: str,
                             dominio: str = "", precio: int = MCR_LOW_PRICE,
                             marca: str = "MCR") -> str:
    """Meta descripcion al estilo de la marca.

    Enfatiza: mejor precio, comparador, seguro de viaje gratis,
    kilometros ilimitados. KW principal: alquiler de autos (o coches en Spain).
    """
    kw = get_kw_autos(dominio, lang)
    brand_name = MARCA.get(marca, "Miles Car Rental")
    brand_pt = brand_name  # igual en PT
    if lang == "EN":
        return (
            f"Rent a Car in {ubicacion} from USD ${precio}/day. "
            f"Compare rates across top agencies, free travel insurance, "
            f"unlimited mileage, and flexible modifications. "
            f"Book online with {brand_name}."
        )
    if lang == "PT":
        return (
            f"Aluguel de {kw} em {ubicacion} a partir de USD ${precio}/dia. "
            f"Compare tarifas das melhores locadoras, seguro de viagem gratis, "
            f"quilometragem ilimitada e modificacoes flexiveis. "
            f"Reserve online na {brand_pt}."
        )
    # ES
    return (
        f"Alquiler de {kw} en {ubicacion} desde USD ${precio}/dia. "
        f"Compara tarifas de las mejores agencias, seguro de viaje gratis, "
        f"kilometros ilimitados y modificaciones flexibles. "
        f"Reserva online en {brand_name}."
    )


def generar_titulo_lp(ubicacion: str, tipo_lp: str, lang: str,
                      dominio: str = "") -> str:
    """Genera el Titulo LP (H1-like) estilo pagina oficial:
      ES: 'ALQUILER DE AUTOS EN {UBICACION} - MEJORES TARIFAS'
      EN: 'CAR RENTAL IN {UBICACION} - BEST RATES'
      PT: 'ALUGUEL DE CARROS EM {UBICACION} - MELHORES TARIFAS'
    """
    kw = get_kw_autos(dominio, lang)
    ub = ubicacion.upper()
    if lang == "EN":
        return f"CAR RENTAL IN {ub} - BEST RATES"
    if lang == "PT":
        return f"ALUGUEL DE {kw.upper()} EM {ub} - MELHORES TARIFAS"
    return f"ALQUILER DE {kw.upper()} EN {ub} - MEJORES TARIFAS"


def _extraer_nombre_ubicacion(lp: dict) -> str:
    """Extrae el nombre representativo de la LP para usar en metas/títulos."""
    tipo = lp["tipo_lp"]
    ciudad = lp.get("ciudad", "")
    localidad = lp.get("localidad", "")
    agencia = lp.get("agencia", "")
    car_cat = lp.get("car_category", "")

    def es_real(val):
        if not val:
            return False
        sentinelas = {"no es localidad", "no es agencia", "no es tipo de autos",
                      "no es ciudad", "no es oferta"}
        return val.strip().lower() not in sentinelas

    # Si la LP no tiene ciudad, usar la del dominio (milescarrentalatlanta.com -> Atlanta)
    dominio = lp.get("dominio", "")
    ciudad_dominio = get_site_city(dominio)

    if tipo == "AGENCIAS" and es_real(agencia):
        if es_real(ciudad):
            return f"{agencia} {ciudad}"
        if ciudad_dominio:
            return f"{agencia} {ciudad_dominio}"
        return agencia
    elif tipo == "TIPOS DE AUTOS" and es_real(car_cat):
        if es_real(ciudad):
            return f"{car_cat} {ciudad}"
        if ciudad_dominio:
            return f"{car_cat} {ciudad_dominio}"
        return car_cat
    elif tipo == "LOCALIDADES" and es_real(localidad) and localidad.lower() != "no es localidad":
        return localidad
    elif es_real(ciudad):
        return ciudad
    elif ciudad_dominio:
        return ciudad_dominio
    return ""


def construir_fila_landing_page(db: sqlite3.Connection, lp_id: int) -> dict:
    """Construye la fila completa para la hoja LandingPage de una LP MCR.

    Retorna dict con claves A-M correspondientes a las columnas.
    """
    lp_row = db.execute("SELECT * FROM landing_pages WHERE id = ?", (lp_id,)).fetchone()
    if not lp_row:
        raise ValueError(f"LP no encontrada: {lp_id}")

    lp = dict(lp_row)
    tipo_lp = lp["tipo_lp"]
    trinomio = obtener_urls_trinomio(db, lp_id)
    url_es = trinomio.get("ES", {}).get("url_path", "")
    ubicacion = _extraer_nombre_ubicacion(lp)

    # Nombre del sitio
    nombre = construir_nombre_sitio(lp)

    # Metas y títulos: usar los de la BD si existen, sino generar
    fila = {
        "A": nombre,
        "B": url_es,
        "C": MCR_HIGH_PRICE,
        "D": MCR_LOW_PRICE,
    }

    dominio = lp.get("dominio", "")
    marca = lp.get("proyecto", "MCR")
    for lang, cols in [("EN", ("E", "F", "G")), ("ES", ("H", "I", "J")), ("PT", ("K", "L", "M"))]:
        url_data = trinomio.get(lang, {})
        col_titulo, col_meta_tit, col_meta_desc = cols

        # Usar datos BD si existen, sino generar
        bd_meta_tit = url_data.get("meta_title", "") or ""
        bd_meta_desc = url_data.get("meta_description", "") or ""

        # Titulo LP: vacio (no se requiere)
        fila[col_titulo] = ""
        fila[col_meta_tit] = bd_meta_tit if bd_meta_tit.strip() else (generar_meta_titulo(ubicacion, tipo_lp, lang, dominio, marca=marca) if ubicacion else "")
        fila[col_meta_desc] = bd_meta_desc if bd_meta_desc.strip() else (generar_meta_descripcion(ubicacion, tipo_lp, lang, dominio, marca=marca) if ubicacion else "")

    return fila


def demo_memphis():
    """Demo: genera la fila LandingPage para Memphis MCR."""
    db = _get_db()
    # Buscar Memphis MCR
    row = db.execute(
        "SELECT id FROM landing_pages WHERE ciudad LIKE '%emphis%' AND proyecto='MCR' LIMIT 1"
    ).fetchone()
    if not row:
        print("No se encontró Memphis MCR en la BD")
        return

    lp_id = row["id"]
    fila = construir_fila_landing_page(db, lp_id)

    print("=" * 70)
    print("HOJA LANDINGPAGE — Memphis MCR")
    print("=" * 70)
    headers = {
        "A": "Nombre del sitio",
        "B": "Url LandingPage",
        "C": "HighPrice",
        "D": "LowPrice",
        "E": "Titulo LP (Ingles)",
        "F": "Meta titulo (Ingles)",
        "G": "Meta descripcion (Ingles)",
        "H": "Titulo Lp (Espanol)",
        "I": "Meta titulo (espanol)",
        "J": "Meta descripcion (Espanol)",
        "K": "Titulo Lp (Portugues)",
        "L": "Meta titulo (Portugues)",
        "M": "Meta descripcion (Portugues)",
    }
    for col in "ABCDEFGHIJKLM":
        print(f"  {col} ({headers[col]}): {fila[col]}")

    db.close()
    return fila


if __name__ == "__main__":
    demo_memphis()
