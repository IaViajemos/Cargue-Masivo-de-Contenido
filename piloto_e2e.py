"""
piloto_e2e.py — Piloto end-to-end: genera 1 LP MCR (Memphis) completa via RIA.

Flujo:
1. Conectar + autenticar
2. Listar templates → elegir MCR ciudad
3. Crear proyecto → obtener LP ID
4. Generar bloques 1-6+ con IA
5. Traducir cada celda a EN y PT
6. Bulk-update secciones
7. Exportar Excel
"""
import sys
import io
import os
import time
import json
import logging

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("piloto")

from ria_client import RIAClient, RIAError

# ── Mapeo block_type → SectionType válido para bulk-update ────────────
# La API solo acepta: quicksearch, fleet, agencies, faq, faq_respuesta,
# car_rental, car_type, fav_city, custom
SECTION_TYPE_MAP = {
    "quicksearch": "quicksearch",
    "fleet": "fleet",
    "reviews": "custom",
    "rentcompanies": "agencies",
    "questions": "faq",
    "advicestipocarrusel": "custom",
    "fleetcarrusel": "car_rental",
    "locationscarrusel": "fav_city",
    "rentacar": "custom",
}

# Config
RIA_URL = "http://192.168.1.129:8000"
# Credenciales
EMAIL = "miguelm@redactoria.com"
PASSWORD = "MiguelMia2025"

ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = ROOT

# Datos del piloto MCR Memphis
PILOTO = {
    "proyecto": "mcr",
    "categoria": "ciudad",
    "dominio": "com",
    "nombre": "Piloto MCR Memphis E2E",
    "tema": "Memphis, Tennessee",
    "bloques": [
        {
            "block_number": 1,
            "block_type": "quicksearch",
            "tit": "Renta de Autos en Memphis",
            "cell_key": "0-3",
        },
        {
            "block_number": 2,
            "block_type": "fleet",
            "tit": "Flota de Alquiler de Autos en Memphis",
            "cell_key": "6-3",
        },
        {
            "block_number": 3,
            "block_type": "reviews",
            "tit": "Reseñas de Alquiler de Autos en Memphis",
            "cell_key": "10-3",
        },
        {
            "block_number": 3,
            "block_type": "rentcompanies",
            "tit": "Compañías de Renta de Autos en Memphis",
            "cell_key": "12-3",
        },
        {
            "block_number": 4,
            "block_type": "questions",
            "tit": "Preguntas Frecuentes sobre Renta de Autos en Memphis",
            "cell_key": "15-3",
            "faq_questions": [
                "¿Cuánto cuesta rentar un auto en Memphis?",
                "¿Qué necesito para alquilar un auto en Memphis?",
                "¿Cuál es la mejor agencia de renta de autos en Memphis?",
                "¿Puedo rentar un auto en Memphis sin tarjeta de crédito?",
            ],
        },
        {
            "block_number": 5,
            "block_type": "fleetcarrusel",
            "tit": "Tipos de Autos en Alquiler en Memphis",
            "cell_key": "42-3",
            "car_types": ["Económico", "Compacto", "SUV", "Camioneta", "Convertible"],
        },
        {
            "block_number": 6,
            "block_type": "locationscarrusel",
            "tit": "Alquiler de Autos en Ciudades Cercanas a Memphis",
            "cell_key": "56-3",
            "fav_city_questions": ["Nashville", "Little Rock", "Jackson", "Birmingham"],
        },
        {
            "block_number": 5,
            "block_type": "rentacar",
            "tit": "Todo sobre Renta de Autos en Memphis",
            "cell_key": "90-3",
        },
    ],
}


def find_template(client: RIAClient, proyecto: str, categoria: str) -> dict:
    """Find the matching template from active templates."""
    templates = client.list_templates()
    log.info("Templates activos: %d", len(templates))

    for t in templates:
        tp = (t.get("proyecto", "") or "").lower()
        tc = (t.get("categoria", "") or "").lower()
        if tp == proyecto.lower() and tc == categoria.lower():
            log.info("Template encontrado: %s (id=%s)", t["name"], t["id"])
            return t

    # Fallback: buscar por nombre parcial
    for t in templates:
        name = (t.get("name", "") or "").lower()
        if proyecto.lower() in name and categoria.lower() in name:
            log.info("Template encontrado (por nombre): %s (id=%s)", t["name"], t["id"])
            return t

    # Mostrar disponibles
    log.warning("No se encontró template para %s/%s. Disponibles:", proyecto, categoria)
    for t in templates:
        log.warning("  - %s | proyecto=%s | categoria=%s | id=%s",
                     t.get("name"), t.get("proyecto"), t.get("categoria"), t.get("id"))
    return None


def extract_content_fields(block_result: dict) -> dict:
    """Extract generated content fields from IAContentResponse."""
    gen = block_result.get("generatedContent", {})

    # structured_content tiene los campos parseados
    sc = gen.get("structured_content", {})
    # processed_fields tiene TODOS los |key: value| extraídos (más completo)
    pf = gen.get("processed_fields", {})
    # additional_content tiene faq_1, desc_1, etc. de las sub-llamadas
    ac = gen.get("additional_content", {})

    # Merge: processed_fields es la fuente más completa, additional_content la complementa
    merged = {}
    merged.update(pf)
    merged.update(sc)
    if ac:
        merged.update(ac)

    return merged


def run_piloto():
    """Ejecuta el piloto end-to-end."""
    t_start = time.time()

    # ── Paso 1: Conectar ──────────────────────────────────────────────
    log.info("="*60)
    log.info("PILOTO E2E — MCR Memphis")
    log.info("="*60)

    log.info("Verificando conectividad con RIA en %s...", RIA_URL)
    try:
        import requests as req
        resp = req.get(f"{RIA_URL}/docs", timeout=5)
        log.info("RIA accesible: %d", resp.status_code)
    except Exception as e:
        log.error("RIA NO accesible en %s: %s", RIA_URL, e)
        log.error("Verifica que Redactoria esté corriendo.")
        return

    # ── Paso 2: Autenticar ────────────────────────────────────────────
    log.info("Autenticando como %s...", EMAIL)
    try:
        client = RIAClient(RIA_URL, EMAIL, PASSWORD)
    except RIAError as e:
        log.error("Error de autenticación: %s", e)
        return

    user = client.whoami()
    log.info("Autenticado: %s %s (%s)", user.get("first_name"), user.get("last_name"), user.get("email"))

    # ── Paso 3: Buscar template ───────────────────────────────────────
    template = find_template(client, PILOTO["proyecto"], PILOTO["categoria"])
    if not template:
        log.error("No se encontró template. Abortando.")
        return

    template_id = template["id"]

    # ── Paso 4: Crear proyecto + LP ───────────────────────────────────
    log.info("Creando proyecto: %s", PILOTO["nombre"])
    try:
        proyecto = client.create_proyecto(
            name=PILOTO["nombre"],
            template_id=template_id,
            description=f"Piloto E2E para {PILOTO['tema']}"
        )
    except RIAError as e:
        log.error("Error creando proyecto: %s", e)
        return

    proyecto_id = proyecto["id"]
    log.info("Proyecto creado: id=%s", proyecto_id)

    # Obtener LP auto-creada
    lp = client.get_landing_page_by_proyecto(proyecto_id)
    lp_id = lp["id"]
    log.info("Landing Page: id=%s, slug=%s", lp_id, lp.get("url_slug"))

    # ── Paso 5: Generar bloques IA ────────────────────────────────────
    log.info("\n" + "─"*60)
    log.info("GENERACIÓN DE CONTENIDO IA")
    log.info("─"*60)

    all_generated = {}  # cell_key -> {field: content}
    block_meta = {}     # block_type -> content fields

    for bloque in PILOTO["bloques"]:
        bt = bloque["block_type"]
        bn = bloque["block_number"]
        tit = bloque["tit"]
        ck = bloque["cell_key"]

        kwargs = {
            "template_proyecto": PILOTO["proyecto"],
            "template_dominio": PILOTO["dominio"],
            "template_categoria": PILOTO["categoria"],
        }
        if "faq_questions" in bloque:
            kwargs["faq_questions"] = bloque["faq_questions"]
        if "car_types" in bloque:
            kwargs["car_types"] = bloque["car_types"]
        if "fav_city_questions" in bloque:
            kwargs["fav_city_questions"] = bloque["fav_city_questions"]
            
        log.info("\n>>> Bloque %d — %s: %s", bn, bt, tit)
        try:
            result = client.generate_block(
                lp_id=lp_id,
                block_number=bn,
                block_type=bt,
                tit=tit,
                tema=PILOTO["tema"],
                cell_key=ck,
                **kwargs,
            )
            fields = extract_content_fields(result)
            block_meta[bt] = fields
            log.info("  Campos generados: %s", list(fields.keys()))

            # Mostrar preview de cada campo
            for k, v in fields.items():
                preview = str(v)[:120].replace('\n', ' ')
                log.info("    %s: %s...", k, preview)

        except RIAError as e:
            log.error("  ERROR en bloque %s: %s", bt, e)
            block_meta[bt] = {"error": str(e)}

    # ── Paso 6: Traducir ──────────────────────────────────────────────
    log.info("\n" + "─"*60)
    log.info("TRADUCCIÓN EN/PT")
    log.info("─"*60)

    translations = {}  # (block_type, field, lang) -> translated text
    translate_count = 0

    for bt, fields in block_meta.items():
        if "error" in fields:
            continue

        for field_name, es_content in fields.items():
            if not es_content or field_name in ("error",):
                continue
            # Solo traducir campos con contenido real (no títulos vacíos)
            if len(str(es_content).strip()) < 5:
                continue

            for lang in ["en", "pt"]:
                try:
                    tr = client.translate(
                        lp_id=lp_id,
                        source_content=str(es_content),
                        target_language=lang,
                        cell_key=f"{bt}-{field_name}-{lang}",
                    )
                    translated = tr.get("translatedContent", "")
                    translations[(bt, field_name, lang)] = translated
                    translate_count += 1

                    if translate_count % 10 == 0:
                        log.info("  Traducciones completadas: %d", translate_count)

                except RIAError as e:
                    log.warning("  Error traduciendo %s/%s/%s: %s", bt, field_name, lang, e)

    log.info("Total traducciones: %d", translate_count)

    # ── Paso 7: Preparar secciones para bulk-update ───────────────────
    log.info("\n" + "─"*60)
    log.info("GUARDANDO SECCIONES (bulk-update)")
    log.info("─"*60)

    # Necesitamos mapear block_type+field → cell_position
    # blocks_metadata está en template['template_config'], NO en /templates/{id}/config
    full_template = client.get_template(template_id)
    template_config = full_template.get("template_config", {})
    blocks_md = template_config.get("blocks_metadata", {})

    sections_to_save = []

    for block_key, bmd in blocks_md.items():
        bt = bmd.get("type", "")
        content_mapping = bmd.get("contentMapping", {})
        title_row = bmd.get("titleRow")

        # Buscar contenido generado para este block_type
        gen_fields = block_meta.get(bt, {})
        if "error" in gen_fields:
            continue

        # section_type válido para la API
        st = SECTION_TYPE_MAP.get(bt, "custom")

        # Guardar título (ES) en la celda del titleRow
        tit_content = gen_fields.get("titulo", "") or gen_fields.get("tit", "")
        if tit_content and title_row is not None:
            # ES (col 3)
            sections_to_save.append({
                "cell_position": f"{title_row}-3",
                "content": tit_content,
                "section_type": st,
            })
            # EN (col 4)
            en_tit = translations.get((bt, "titulo", "en")) or translations.get((bt, "tit", "en"), "")
            if en_tit:
                sections_to_save.append({
                    "cell_position": f"{title_row}-4",
                    "content": en_tit,
                    "section_type": st,
                })
            # PT (col 5)
            pt_tit = translations.get((bt, "titulo", "pt")) or translations.get((bt, "tit", "pt"), "")
            if pt_tit:
                sections_to_save.append({
                    "cell_position": f"{title_row}-5",
                    "content": pt_tit,
                    "section_type": st,
                })

        # Guardar campos de contenido según contentMapping
        for field_name, cell_pos in content_mapping.items():
            es_val = gen_fields.get(field_name, "")

            # Mapeo especial: FAQs usan faq_N en RIA pero desc_N en contentMapping
            if not es_val and bt in ("questions", "faqs") and field_name.startswith("desc_"):
                n = field_name.split("_")[1]
                es_val = gen_fields.get(f"faq_{n}", "")

            if not es_val:
                continue

            row, col = cell_pos.split("-")
            # ES (col 3)
            sections_to_save.append({
                "cell_position": f"{row}-3",
                "content": es_val,
                "section_type": st,
            })
            # EN (col 4) — buscar tanto field_name como faq_N
            en_val = translations.get((bt, field_name, "en"), "")
            if not en_val and bt in ("questions", "faqs") and field_name.startswith("desc_"):
                n = field_name.split("_")[1]
                en_val = translations.get((bt, f"faq_{n}", "en"), "")
            if en_val:
                sections_to_save.append({
                    "cell_position": f"{row}-4",
                    "content": en_val,
                    "section_type": st,
                })
            # PT (col 5)
            pt_val = translations.get((bt, field_name, "pt"), "")
            if not pt_val and bt in ("questions", "faqs") and field_name.startswith("desc_"):
                n = field_name.split("_")[1]
                pt_val = translations.get((bt, f"faq_{n}", "pt"), "")
            if pt_val:
                sections_to_save.append({
                    "cell_position": f"{row}-5",
                    "content": pt_val,
                    "section_type": st,
                })

    log.info("Secciones a guardar: %d", len(sections_to_save))

    if sections_to_save:
        try:
            saved = client.bulk_update_secciones(lp_id, sections_to_save)
            log.info("Secciones guardadas: %d", len(saved))
        except RIAError as e:
            log.error("Error en bulk-update: %s", e)

    # ── Paso 8: Exportar Excel ────────────────────────────────────────
    log.info("\n" + "─"*60)
    log.info("EXPORTANDO EXCEL")
    log.info("─"*60)

    # Construir template_info
    template_info = {
        "id": template_id,
        "name": template.get("name", "Template Ciudad"),
        "description": template.get("description", ""),
        "categoria": PILOTO["categoria"],
        "proyecto": PILOTO["proyecto"],
        "dominio": PILOTO["dominio"],
        "is_active": True,
    }

    # Construir cell_data desde las secciones guardadas
    cell_data = {}
    for sec in sections_to_save:
        cp = sec["cell_position"]
        cell_data[cp] = {"value": sec["content"]}

    # Transformar templateData: DB almacena {text, color} pero API espera {value}
    td = template_config.get("templateData", {})
    fixed_td = {}
    for k, v in td.items():
        if isinstance(v, dict) and "value" not in v:
            fixed_td[k] = {"value": v.get("text", "")}
        else:
            fixed_td[k] = v
    template_config_export = dict(template_config)
    template_config_export["templateData"] = fixed_td

    try:
        xlsx_bytes = client.export_excel(template_config_export, template_info, cell_data)
        output_path = os.path.join(OUTPUT_DIR, f"piloto_mcr_memphis.xlsx")
        with open(output_path, "wb") as f:
            f.write(xlsx_bytes)
        log.info("Excel exportado: %s (%.1f KB)", output_path, len(xlsx_bytes)/1024)
    except RIAError as e:
        log.error("Error exportando Excel: %s", e)

    # ── Resumen ───────────────────────────────────────────────────────
    elapsed = time.time() - t_start
    log.info("\n" + "="*60)
    log.info("PILOTO COMPLETADO en %.1f segundos (%.1f min)", elapsed, elapsed/60)
    log.info("="*60)
    log.info("Proyecto ID: %s", proyecto_id)
    log.info("LP ID: %s", lp_id)
    log.info("Bloques generados: %d", len([b for b in block_meta.values() if "error" not in b]))
    log.info("Traducciones: %d", translate_count)
    log.info("Secciones guardadas: %d", len(sections_to_save))

    # Guardar log de resultados en JSON
    log_data = {
        "proyecto_id": proyecto_id,
        "lp_id": lp_id,
        "template_id": template_id,
        "bloques": {bt: {k: str(v)[:200] for k, v in f.items()} for bt, f in block_meta.items()},
        "traducciones_count": translate_count,
        "secciones_count": len(sections_to_save),
        "elapsed_seconds": round(elapsed, 1),
    }
    log_path = os.path.join(OUTPUT_DIR, "piloto_resultado.json")
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)
    log.info("Log de resultados: %s", log_path)


if __name__ == "__main__":
    run_piloto()
