"""
lm_client.py — Cliente directo para LM Studio (bypass de RIA).

Llama al endpoint OpenAI-compatible de LM Studio para generar contenido SEO
de landing pages MCR y VJM con prompts personalizados.

URL: http://192.168.1.36:1234
Modelo: openai/gpt-oss-20b

RANGOS DE PALABRAS POR BLOQUE (specs oficiales):

MCR (Ciudad):
  B1 quicksearch:      H1 desc 15-20p
  B2 fleet:            H2 desc 125-130p (×3: LATAM/USA/BRA)
  B3 questions:        H2 desc 40-45p  / FAQ resp variable
  B4 reviews:          H2 desc 35-40p
  B5 rentcompanies:    H2 desc 80-85p
  B6 advicestipocarrusel: H2 60-65p / cluster 30-80p
  B7 fleetcarrusel:    H2 80-85p / H3 15-20p
  B8 locationscarrusel: H2 75-80p / H3 25-30p
  B9 rentacar:         H2 100-130p / H3 220-250p

MCR2 (sin consejos):
  B1 quicksearch:      H1 desc 15-20p
  B2 fleet:            H2 desc 125-130p
  B3 rentcompanies:    H2 desc 80-85p
  B4 reviews:          H2 desc 35-40p
  B5 questions:        H2 desc 40-45p
  B6 locationscarrusel: H2 75-80p / H3 25-30p
  B7 rentacar:         H2 100-130p / H3 220-250p

VJM:
  B1 quicksearch:      H1 desc 15-20p
  B2 sectionCars:      H2 desc 80-85p
  B3 agencies:         H2 50-65p / H3 20-35p
  B4 rentalCarFaqs:    H2 55-60p / cluster 25-30p
  B5 favoriteCities:   H2 55-60p
"""
import re
import logging
import requests
from typing import Optional

log = logging.getLogger("lm_client")

LM_STUDIO_URL = "http://192.168.1.36:1234"
LM_MODEL = "openai/gpt-oss-20b"
# Temperaturas por bloque segun flexibilidad necesaria:
LM_TEMPERATURE = 0.55          # default balanceado
LM_TEMP_PRECISE = 0.3          # beneficios IPs, rentcompanies, faq_answers (estructurado)
LM_TEMP_CREATIVE = 0.75        # rentacar mini-blog, quicksearch, carRental (creativo)
LM_TEMP_SUPERVISOR = 0.2       # supervisores SEO (correccion consistente)
LM_TRANSLATE_TEMP = 0.2

# ── System messages ──────────────────────────────────────────────────

_RESTRICCIONES = (
    "Restricciones de estructura:\n"
    "- Nunca usarás emojis\n"
    "- Evita repetir la ciudad/estado constantemente\n"
    "- PROHIBIDO empezar con 'Descubre' o 'Descubrir'\n"
    "- PALABRAS SOBREUSADAS (máximo 1 vez por texto): 'Descubre', "
    "'Encuentra', '¡Disfruta!', 'Aprovecha'. Varía con: "
    "'Explora', 'Vive', 'Prueba', 'Reserva', 'Conoce', 'Siente', "
    "'Accede', 'Recorre', preguntas directas, etc.\n"
    "- Nunca usarás doble ** para negrita\n"
    "- Mantén el número de palabras indicado\n"
    "- Bloques con '|': |tit: contenido| |desc: contenido|\n"
    "- Solo usa | al inicio y final de cada bloque, NUNCA dentro.\n\n"
    "ORTOGRAFÍA ESTRICTA:\n"
    "- TODAS las tildes: vehículo, económico, kilómetro, también, más, "
    "además, fácil, aquí, así, tendrás, podrás, selección, información.\n"
    "- Concordancia género/número correcta.\n"
    "- Sin espacios antes de signos de puntuación.\n"
    "- Porcentajes SIN espacio: '35%' nunca '35 %'.\n"
    "- Capitalización normal (no ALL CAPS excepto siglas).\n"
)

_SEMANTICA = (
    "\nDISTRIBUCIÓN DE SINÓNIMOS (obligatoria en TODO el texto):\n"
    "- 'auto/autos': 70% de las menciones (keyword principal)\n"
    "- 'carro/carros': 29% de las menciones\n"
    "- 'vehículo/vehículos': máximo 1 vez por texto\n"
    "- 'coche/coches': MÁXIMO 1 única vez en TODA la landing, al final\n"
    "Usar singular y plural según contexto natural.\n"
    "Verbos: Alquiler / Renta (alternar libremente).\n\n"
    "Palabras y frases ABSOLUTAMENTE PROHIBIDAS:\n"
    "- Automóvil, Flota\n"
    "- 'cargos ocultos', 'gastos ocultos', 'pagos ocultos', "
    "'costos ocultos', 'sin sorpresas'\n"
    "- 'Descuentos relámpago'\n"
    "- 'furgonetas' (usa 'vans')\n"
    "- 'SUVs' (con s) → siempre 'SUV' sin s\n"
    "- 'autos tipo SUV', 'autos tipo Van' (suena artificial)\n"
    "- Inventar beneficios que NO están en la tabla oficial\n\n"
    "TIPOS DE VEHÍCULO — uso natural y contextual:\n"
    "  ✓ 'Alquiler de SUV en Miami' / 'Renta una SUV y recorre...'\n"
    "  ✓ 'Renta de Vans en Orlando' / 'Alquila una Van para tu grupo'\n"
    "  ✓ 'Alquiler de autos convertibles' / 'Renta de autos de lujo'\n"
    "  ✗ 'SUVs' (NUNCA con s final)\n"
    "  ✗ 'autos tipo SUV' o 'autos tipo Van' (artificial)\n\n"
    "DENSIDAD DE KW:\n"
    "No pueden aparecer 2 keywords principales (alquiler de autos, "
    "renta de carros, etc.) en menos de 50 palabras de distancia "
    "dentro del mismo párrafo.\n\n"
    "KEYWORDS SEO POR TIPO DE LANDING PAGE:\n"
    "(a) CIUDAD: 'alquiler de autos en {CIUDAD}' / 'renta de autos en {CIUDAD}'\n"
    "(b) LOCALIDAD: 'alquiler de autos en {LOCALIDAD}'\n"
    "(c) AGENCIA: 'alquiler de autos con {AGENCIA}' o '{AGENCIA} en {CIUDAD}'\n"
    "(d) TIPO DE AUTO: 'alquiler de autos de lujo' / 'alquiler de SUV en {CIUDAD}'\n\n"
    "FORMATO: porcentajes SIN espacio: '35%' nunca '35 %'.\n"
)

_ESTILO_MCR = (
    "\nESTILO DE MARCA - Miles Car Rental:\n"
    "- Miles Car Rental es un COMPARADOR de tarifas de renta de autos que "
    "trabaja con múltiples agencias aliadas (Alamo, Avis, Hertz, Budget, "
    "Dollar, Enterprise, etc.). Conecta al usuario con las mejores tarifas.\n"
    "- Tono: SERIO, profesional, confiable. Enfatiza trayectoria (\"más de "
    "15 años\"), alianzas con agencias prestigiosas y beneficios incluidos.\n"
    "- Público: viajeros adultos/corporativos que buscan confiabilidad.\n"
    "- Frases cortas y directas. Sin rodeos. Datos concretos.\n"
    "- Máximo 1 exclamación por párrafo (no excesivas).\n"
    "- Sin preguntas retóricas en el cuerpo (solo en títulos FAQ).\n"
    "- Usa: 'Miles Car Rental te conecta con las mejores agencias', "
    "'compara y reserva', 'reserva online', 'más de 15 años'.\n"
    "- BENEFICIOS EXACTOS (SOLO estos, no inventar):\n"
    "   * LATAM (desc): Seguro de Viaje Gratis (para extranjeros), "
    "Kilómetros Ilimitados, Asistencia Básica en Carretera, "
    "Modificaciones Flexibles.\n"
    "   * IP USA: Kilómetros Ilimitados, Asistencia Básica en Carretera, "
    "Modificaciones sin cargos administrativos (NO Seguro de Viaje Gratis, NO IOF).\n"
    "   * IP BRA: Seguro de Viaje Gratis, Kilómetros Ilimitados, "
    "Modificaciones Flexibles, Beneficio en Cobertura del IOF.\n"
    "- PROHIBIDO inventar beneficios extra como 'seguro contra accidentes', "
    "'asistencia premium', 'conductor adicional gratis', 'GPS gratis' — "
    "SOLO los beneficios listados arriba.\n"
)

_ESTILO_VJM = (
    "\nESTILO DE MARCA - Viajemos:\n"
    "- Viajemos es un COMPARADOR de tarifas de renta de autos que trabaja "
    "con múltiples agencias aliadas (Alamo, Avis, Hertz, Budget, Dollar, "
    "Enterprise, etc.). Conecta al usuario con las mejores tarifas.\n"
    "- Tono: JOVIAL, fresco, cercano, entusiasta. Vocabulario dinámico, "
    "exclamaciones, apelación directa al viajero 'de aventura'.\n"
    "- Público: viajeros jóvenes, turistas, grupos de amigos/familia.\n"
    "- Usa '¡Compara ahora!', '¡Encuentra la mejor tarifa!', "
    "'¡Anímate!', '¡Listo para tu próxima aventura!', 'Con Viajemos'.\n"
    "- Enfatiza: variedad de agencias, ahorro al comparar, sin costos extra, "
    "libertad de viaje, diversión.\n"
    "- NO uses 'nuestra flota', 'nuestros autos' (Viajemos no tiene autos "
    "propios). SÍ usa 'los mejores precios', 'las mejores agencias'.\n"
)

SYSTEM_MCR = (
    "Vas a pensar en español, recibirás instrucciones en español y deberás "
    "responder en español (español neutral latinoamericano).\n"
    "Eres un redactor experto en marketing digital SEO, especializado en "
    "contenidos para Miles Car Rental, un COMPARADOR de tarifas de renta "
    "de autos con alianzas con múltiples agencias reconocidas. "
    "Tono serio y profesional.\n"
    + _RESTRICCIONES + _SEMANTICA + _ESTILO_MCR
)

SYSTEM_VJM = (
    "Vas a pensar en español, recibirás instrucciones en español y deberás "
    "responder en español (español neutral latinoamericano).\n"
    "Eres un redactor experto en marketing digital SEO, especializado en "
    "contenidos para Viajemos, un COMPARADOR de tarifas de renta de autos "
    "con alianzas con múltiples agencias reconocidas. Tono jovial y dinámico.\n"
    + _RESTRICCIONES + _SEMANTICA + _ESTILO_VJM
)

_BENEFICIOS_FLEET = (
    "\nTabla de beneficios Miles Car Rental:\n"
    "LATAM (público general, extranjeros visitando el destino):\n"
    "  - Seguro de Viaje Gratis para extranjeros\n"
    "  - Kilómetros Ilimitados\n"
    "  - Asistencia Básica en Carretera\n"
    "  - Modificaciones Flexibles\n"
    "IP USA (residentes de USA que rentan localmente):\n"
    "  - Kilómetros Ilimitados\n"
    "  - Asistencia Básica en Carretera\n"
    "  - Modificaciones sin cargos administrativos\n"
    "  (NO incluyen Seguro de Viaje Gratis ni Conductor Adicional)\n"
    "IP BRA (residentes de Brasil visitando el destino):\n"
    "  - Seguro de Viaje Gratis para extranjeros\n"
    "  - Kilómetros Ilimitados\n"
    "  - Modificaciones Flexibles\n"
    "  - Beneficio en Cobertura del IOF\n"
)

SYSTEM_TRANSLATE_EN = (
    "You are a professional translator. Translate the following Spanish text "
    "to US English.\n"
    "Maintain the exact same formatting, structure, and pipe delimiters "
    "|key: value|.\n"
    "Keep brand names unchanged: Miles Car Rental, Viajemos.\n"
    "Translate naturally for a US English audience.\n"
    "Preserve bullet points (* item) and line breaks.\n"
    "ONLY output the translation, nothing else."
)

SYSTEM_TRANSLATE_PT = (
    "Você é um tradutor profissional. Traduza o seguinte texto em espanhol "
    "para português brasileiro.\n"
    "Mantenha exatamente a mesma formatação, estrutura e delimitadores "
    "|chave: valor|.\n"
    "Mantenha os nomes de marcas: Miles Car Rental, Viajemos.\n"
    "Traduza naturalmente para o público brasileiro.\n"
    "Mantenha marcadores (* item) e quebras de linha.\n"
    "Responda APENAS com a tradução, nada mais."
)


class LMClient:
    """Cliente para LM Studio API (OpenAI-compatible)."""

    def __init__(self, base_url: str = LM_STUDIO_URL, model: str = LM_MODEL,
                 brand: str = "mcr"):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.brand = brand.lower()  # "mcr" o "vjm"
        self.session = requests.Session()

    @property
    def system_seo(self) -> str:
        return SYSTEM_VJM if self.brand == "vjm" else SYSTEM_MCR

    @property
    def brand_name(self) -> str:
        return "Viajemos" if self.brand == "vjm" else "Miles Car Rental"

    def _call(self, system: str, user: str, temperature: float = LM_TEMPERATURE,
              max_tokens: int = 6000) -> str:
        resp = self.session.post(
            f"{self.base_url}/v1/chat/completions",
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=600,  # 10 min por llamada (no hay prisa, prioridad estabilidad)
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"] or ""

    def _generate_field(self, prompt: str, field_name: str,
                        system: str = "", max_tokens: int = 6000,
                        retries: int = 4, min_words: int = 5,
                        supervise: bool = True) -> str:
        """Genera un campo con pipeline 3-pass (estilo RIA) + fallback.

        Pipeline:
          1. generate: crea contenido inicial
          2. supervisor_seo: corrige KWs, beneficios, palabras restringidas
          3. supervisor_structure: valida formato pipe y cuenta de palabras

        Garantia: NUNCA devuelve vacio. Si falla todo, fallback template.
        """
        sys_msg = system or self.system_seo
        value = ""
        for attempt in range(retries + 1):
            raw = self._call(sys_msg, prompt, max_tokens=max_tokens)
            fields = self.parse_fields(raw)
            value = fields.get(field_name, "").strip()
            # Si el pipe no se parseo, intentar extraer texto crudo
            if not value or len(value.split()) < min_words:
                cleaned = self._extract_raw_field(raw, field_name)
                if cleaned and len(cleaned.split()) >= min_words:
                    value = cleaned
            if value and len(value.split()) >= min_words:
                # Aplicar supervisores
                if supervise:
                    value = self.supervisor_seo(value, field_name) or value
                    value = self.supervisor_structure(value, field_name) or value
                if value and len(value.split()) >= min_words:
                    return value
            if attempt < retries:
                log.warning("Campo '%s' intento %d/%d insuficiente, reintentando...",
                            field_name, attempt + 1, retries + 1)
        log.error("Campo '%s' vacio tras %d intentos - usando fallback", field_name, retries + 1)
        # Fallback: si todo falla, construir un texto minimo desde el prompt
        if not value or len(value.split()) < min_words:
            value = self._fallback_text(field_name, prompt)
        return value

    @staticmethod
    def _extract_raw_field(raw: str, field_name: str) -> str:
        """Extrae texto crudo cuando el LLM no uso formato pipe."""
        raw = raw.strip()
        # Remover wrappers comunes
        raw = re.sub(r'^\|?\s*\w+\s*:\s*', '', raw)
        raw = re.sub(r'\s*\|\s*$', '', raw)
        # Remover think tags si quedaron
        raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL)
        return raw.strip()

    def _fallback_text(self, field_name: str, prompt: str) -> str:
        """Fallback minimo cuando el LLM falla completamente."""
        # Extraer contexto (ciudad, etc) del prompt si es posible
        m = re.search(r"Nuevo tema:\s*([^,\n]+)", prompt)
        ctx = m.group(1).strip() if m else "el destino seleccionado"
        return (
            f"Disfruta del alquiler de autos en {ctx} con Miles Car Rental. "
            f"Compara tarifas de las mejores agencias, aprovecha kilometros "
            f"ilimitados, modificaciones flexibles y descuentos exclusivos. "
            f"Reserva online y asegura el mejor precio para tu proximo viaje."
        )

    # ══════════════════════════════════════════════════════════════════
    # SUPERVISORES (estilo RIA: SEO + estructura)
    # ══════════════════════════════════════════════════════════════════

    def supervisor_seo(self, text: str, field_name: str = "") -> str:
        """Pass 2 - Supervisor SEO: corrige KWs, beneficios, ortografia.

        Revisa el texto y aplica:
        - Homologaciones (Alquiler/Renta, Autos/Carros/Vehiculos)
        - Palabras restringidas (Coche, Automovil, Flota) -> sustituir
        - Mapeo de beneficios (tabla estandar)
        - KW principal "alquiler de autos" (no aislar el tipo)
        - Ortografia y claridad
        Si el texto esta bien, devuelve igual.
        """
        if not text or len(text.split()) < 5:
            return text

        system_sup = (
            "Eres un supervisor SEO y editor experto en español neutral latinoamericano. "
            "Tu tarea es revisar y corregir el texto manteniendo el sentido original "
            "y el conteo aproximado de palabras.\n\n"
            "REGLAS CRÍTICAS:\n"
            "1. SINÓNIMOS: 'auto/autos' 70%, 'carro/carros' 29%, "
            "'vehículo' máx 1 vez. 'SUVs' → 'SUV' (sin s). "
            "'autos tipo SUV' → 'SUV'. 'furgonetas' → 'vans'.\n"
            "2. PROHIBIDAS: Automóvil, Flota, cargos ocultos, sin sorpresas, "
            "descuentos relámpago. Si aparecen → eliminar o sustituir.\n"
            "3. DENSIDAD KW: NO pueden aparecer 2 keywords principales "
            "(alquiler de autos, renta de carros, etc.) en menos de 50 "
            "palabras de distancia en el mismo párrafo. Si están muy juntas, "
            "reformula una de ellas sin perder el sentido.\n"
            "4. ORTOGRAFÍA EXHAUSTIVA:\n"
            "   - Verificar TODAS las tildes: vehículo, económico, kilómetro, "
            "también, más, además, fácil, aquí, así, selección, información, "
            "tendrás, podrás, compañía, categoría, garantía.\n"
            "   - Concordancia género/número correcta.\n"
            "   - Porcentajes SIN espacio: '35%' nunca '35 %'.\n"
            "   - Sin espacios antes de signos de puntuación.\n"
            "5. REPETICIONES: si empieza con 'Descubre' → reescribir apertura. "
            "Máx 1 uso por texto de: Descubre, Encuentra, Aprovecha, Disfruta.\n"
            "6. NO agregues contenido nuevo. Solo corrige lo existente.\n"
            "7. Preserva saltos de línea y formato del original.\n"
            "8. Responde SOLO con el texto corregido, sin comentarios."
        )
        user = f"Texto a revisar (campo '{field_name}'):\n\n{text}\n\nTexto corregido:"
        try:
            corrected = self._call(system_sup, user, temperature=0.2, max_tokens=3000)
            corrected = corrected.strip()
            # Remover wrappers de pipe si el supervisor los agrego
            corrected = re.sub(r'^\|?\s*\w+\s*:\s*', '', corrected)
            corrected = re.sub(r'\s*\|\s*$', '', corrected)
            corrected = re.sub(r'<think>.*?</think>', '', corrected, flags=re.DOTALL).strip()
            # Validar que no se haya reducido excesivamente
            if corrected and len(corrected.split()) >= max(5, len(text.split()) // 2):
                return corrected
        except Exception as e:
            log.warning("supervisor_seo fallo: %s", e)
        return text

    def supervisor_structure(self, text: str, field_name: str = "") -> str:
        """Pass 3 - Supervisor estructura: valida formato y estructura.

        Verifica que:
        - Listas usan '- ' con saltos de linea y envoltorio '**'
        - Sub-titulos usan '*h4 titulo *h4'
        - No hay etiquetas de marcado sin cerrar
        - No quedan restos de pipe format
        """
        if not text or len(text.split()) < 5:
            return text

        # Limpieza automatica (sin LLM)
        cleaned = text

        # Remover pipes sueltos internos (no al inicio/fin)
        cleaned = re.sub(r'(?<!^)\|(?!\s*$)', '', cleaned)

        # Normalizar listas: asegurar que '- item' tenga salto de linea antes
        # Si hay patron "texto. - item - item" sin saltos, inyectar \n
        if ' - ' in cleaned and '\n- ' not in cleaned:
            # Solo si parece ser una lista (3+ guiones seguidos)
            if cleaned.count(' - ') >= 2:
                cleaned = re.sub(r'(?<=[\.\:\!])\s+-\s+', '\n- ', cleaned)
                cleaned = re.sub(r'(?<=[a-záéíóúñ\.])\s+-\s+(?=[A-ZÁ])', '\n- ', cleaned)

        # Asegurar que ** este en linea propia si abre/cierra una lista
        cleaned = re.sub(r'([^\n])\*\*(\s*\n)', r'\1\n**\2', cleaned)
        cleaned = re.sub(r'(\n\s*)\*\*(?!\n)([^\n])', r'\1**\n\2', cleaned)

        # Remover etiquetas markdown restantes que no usamos
        cleaned = re.sub(r'^#{1,6}\s*', '', cleaned, flags=re.MULTILINE)

        # Remover think tags residuales
        cleaned = re.sub(r'<think>.*?</think>', '', cleaned, flags=re.DOTALL).strip()

        # Normalizar saltos: maximo 2 seguidos (parrafo)
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        # NBSP y caracteres raros
        cleaned = cleaned.replace('\u202f', ' ').replace('\u00a0', ' ')
        cleaned = re.sub(r'  +', ' ', cleaned)

        # Filtro final de frases prohibidas (cargos ocultos, se alia con agencias, etc.)
        cleaned = self._strip_banned(cleaned)

        return cleaned.strip() if cleaned.strip() else text

    # ──────────────────────────────────────────────────────────────────
    # Helpers para supervisar fields dict + garantizar no-vacio
    # ──────────────────────────────────────────────────────────────────

    def supervise_fields(self, fields: dict,
                         required_keys: Optional[list] = None,
                         min_words: int = 5,
                         supervise: bool = True,
                         prompt_ctx: str = "") -> dict:
        """Aplica supervisores a cada campo y garantiza que los required_keys
        tengan contenido minimo. Si alguno esta vacio, usa fallback.
        """
        required_keys = required_keys or []
        out = dict(fields)
        for key, val in list(out.items()):
            if not isinstance(val, str):
                continue
            if not val.strip() or len(val.split()) < min_words:
                continue
            if supervise and key != "tit":  # no supervisar titulos (cortos)
                val2 = self.supervisor_seo(val, key) or val
                val2 = self.supervisor_structure(val2, key) or val2
                out[key] = val2

        # Garantizar required_keys no vacios
        for k in required_keys:
            v = out.get(k, "")
            if not v or (isinstance(v, str) and len(v.split()) < min_words):
                log.warning("supervise_fields: '%s' vacio, aplicando fallback", k)
                out[k] = self._fallback_text(k, prompt_ctx)
        return out

    def ping(self) -> list:
        resp = self.session.get(f"{self.base_url}/v1/models", timeout=10)
        resp.raise_for_status()
        return [m["id"] for m in resp.json().get("data", [])]

    # ── Parseo ─────────────────────────────────────────────────────────

    @staticmethod
    def parse_fields(text: str) -> dict:
        fields = {}
        pattern = r'\|\s*(\w+)\s*:\s*(.*?)\s*\|'
        for match in re.finditer(pattern, text, re.DOTALL):
            key = match.group(1).strip()
            value = match.group(2).strip()
            fields[key] = value
        return fields

    # ══════════════════════════════════════════════════════════════════
    # BLOQUES MCR
    # ══════════════════════════════════════════════════════════════════

    def generate_quicksearch(self, ciudad: str, estado: str = "",
                             tit: str = "") -> dict:
        """B1: quicksearch — H1 + desc 15-20 palabras."""
        if not tit:
            tit = f"Renta de Autos en {ciudad}"
            if estado:
                abbr = estado[:2].upper()
                tit += f", {abbr}"
        ubicacion = f"{ciudad}, {estado}" if estado else ciudad

        prompt = (
            "Ejemplos de referencia:\n"
            "Ejemplo 1: tit: Renta de Autos en Orlando, FL, "
            "desc: ¡Priorizamos tu ahorro y garantizamos más beneficios! "
            "Encuentra aquí el mejor precio en renta de carros en Orlando, Florida\n"
            "Ejemplo 2: tit: Alquiler de Autos en San Antonio, TX, "
            "desc: ¡Priorizamos tu ahorro y garantizamos más beneficios! "
            "Encuentra aquí el mejor precio en alquiler de vehículos en San Antonio\n\n"
            f"Nuevo tema: {ubicacion}, tit: {tit}\n"
            "Reglas para desc: EXACTAMENTE 15 a 20 palabras.\n"
            "Genera:\n"
            f"|tit: {tit}|\n"
            "|desc: tu redacción|"
        )
        raw = self._call(self.system_seo, prompt, max_tokens=2000)
        fields = self.parse_fields(raw)
        if "tit" not in fields:
            fields["tit"] = tit
        return fields

    # Beneficios por audiencia MCR (para reemplazo quirurgico en fleet)
    _MCR_BENEFICIOS_LATAM = (
        "Seguro de Viaje Gratis para extranjeros, Kilómetros Ilimitados, "
        "Asistencia Básica en Carretera, Modificaciones Flexibles"
    )
    _MCR_BENEFICIOS_USA = (
        "Kilómetros Ilimitados, Conductor Adicional sin Costo extra, "
        "Asistencia Básica en Carretera, Modificaciones Flexibles"
    )
    _MCR_BENEFICIOS_BRA = (
        "Seguro de Viaje Gratis para extranjeros, Kilómetros Ilimitados, "
        "Asistencia Básica en Carretera, Modificaciones Flexibles, "
        "Beneficio en Cobertura del IOF"
    )

    def generate_fleet(self, ciudad: str, estado: str = "",
                       tit: str = "") -> dict:
        """B2: fleet MCR — genera 1 texto base (LATAM) y crea USA/BRA
        por reemplazo quirurgico de la frase de beneficios.

        El texto es IDENTICO en las 3 versiones; solo cambia la lista
        de beneficios que aparece en el segundo parrafo.
        """
        if not tit:
            tit = f"Ofertas en alquiler de carros en {ciudad}"
            if estado:
                tit += f", {estado}"
        ubicacion = f"{ciudad}, {estado}" if estado else ciudad

        # 1. Generar UN solo texto base (H2/LATAM) con apertura rotativa
        import hashlib
        _aperturas = [
            f"¿Planeas un viaje a {ciudad}? Compara tarifas de alquiler de autos con descuentos hasta del 35%",
            f"Tu próximo recorrido por {ciudad} empieza con la tarifa ideal. Accede a descuentos hasta del 35%",
            f"En {ciudad} te esperan rutas increíbles. Alquila un auto con descuentos hasta del 35%",
            f"¿Listo para {ciudad}? Accede a las mejores tarifas de renta de autos con hasta 35% de descuento",
            f"Recorre {ciudad} sin límites. Con descuentos hasta del 35% en alquiler de autos",
            f"{ciudad} tiene todo para ti. Elige entre compactos, SUV, vans, convertibles y autos de lujo",
        ]
        # Seleccionar apertura determinista por hash del nombre
        idx = int(hashlib.md5(ubicacion.encode()).hexdigest(), 16) % len(_aperturas)
        apertura = _aperturas[idx]

        prompt = (
            f"Redacta UN texto de 120-130 palabras sobre alquiler de autos en "
            f"{ubicacion} para Miles Car Rental.\n\n"
            f"EMPIEZA CON ESTA APERTURA (puedes ajustarla levemente):\n"
            f"'{apertura}'\n\n"
            f"ESTRUCTURA (2 párrafos):\n"
            f"Párrafo 1: La apertura indicada + variedad de vehículos "
            f"(compactos, SUV, vans, convertibles, lujo). Disponibilidad "
            f"en ciudades y aeropuertos.\n"
            f"Párrafo 2: Beneficios exclusivos. INCLUYE EXACTAMENTE: "
            f"'{self._MCR_BENEFICIOS_LATAM} y mucho más'. "
            f"Cierre con trayectoria de más de 15 años, invitar a reservar.\n\n"
            f"IMPORTANTE:\n"
            f"- Texto continuo, sin saltos extra.\n"
            f"- Capitalización normal.\n"
            f"- Los beneficios TEXTUALMENTE como se indica.\n"
            f"- Porcentajes sin espacio: '35%' no '35 %%'.\n\n"
            f"|desc: tu texto completo|"
        )

        desc = self._generate_field(prompt, "desc", system=self.system_seo,
                                     max_tokens=4000, min_words=80, retries=4,
                                     supervise=False)  # sin supervisar, lo hacemos manual

        # 2. Crear IP USA y IP BRA por reemplazo quirurgico
        ip_usa = desc.replace(self._MCR_BENEFICIOS_LATAM, self._MCR_BENEFICIOS_USA)
        ip_bra = desc.replace(self._MCR_BENEFICIOS_LATAM, self._MCR_BENEFICIOS_BRA)

        # Si el reemplazo no encontro la frase exacta, intentar variantes
        if ip_usa == desc:
            log.warning("fleet MCR: reemplazo USA no encontro frase exacta, buscando variante")
            ip_usa = self._fleet_swap_benefits(desc, "usa")
        if ip_bra == desc:
            log.warning("fleet MCR: reemplazo BRA no encontro frase exacta, buscando variante")
            ip_bra = self._fleet_swap_benefits(desc, "bra")

        # Limpiar
        desc = self._clean_fleet_text(desc, "desc")
        ip_usa = self._clean_fleet_text(ip_usa, "ip_usa")
        ip_bra = self._clean_fleet_text(ip_bra, "ip_bra")

        fields = {
            "tit": tit,
            "desc": desc,
            "ip_usa": ip_usa,
            "ip_bra": ip_bra,
        }

        # Garantia: si desc vacio, usar template
        for k in ("desc", "ip_usa", "ip_bra"):
            if not fields.get(k) or len(fields.get(k, "").split()) < 30:
                log.error("fleet MCR: '%s' vacio, usando template", k)
                fields[k] = self._fleet_template(k, ubicacion)

        return fields

    def _fleet_swap_benefits(self, text: str, target: str) -> str:
        """Busca variantes de la frase de beneficios LATAM en el texto
        y la reemplaza por la version USA o BRA."""
        import re
        # Buscar patron: lista de beneficios entre marcadores comunes
        # "ventajas exclusivas como XXXX y mucho más"
        # "beneficios: XXXX y mucho más"
        # "accede a XXXX. Todo"
        patterns = [
            (r'(como\s+)(.+?)((?:\s+y mucho más|\s+y más))', 2),
            (r'(accede a\s+)(.+?)(\.\s)', 2),
            (r'(incluye[n]?\s+)(.+?)((?:\s+y mucho más|\.\s))', 2),
        ]
        replacement = self._MCR_BENEFICIOS_USA if target == "usa" else self._MCR_BENEFICIOS_BRA
        for pat, group_idx in patterns:
            m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
            if m and len(m.group(group_idx).split()) >= 5:
                old = m.group(group_idx)
                return text.replace(old, replacement)
        # Si nada funciona, devolver el texto base
        return text

    def _fleet_template(self, campo: str, ubicacion: str) -> str:
        """Template de fallback cuando el LLM falla en fleet."""
        beneficios_map = {
            "desc": ("Seguro de Viaje Gratis, Kilometros Ilimitados, "
                     "Asistencia Basica en Carretera y Modificaciones Flexibles"),
            "ip_usa": ("Kilometros Ilimitados, Asistencia Basica en Carretera y "
                       "Modificaciones sin Cargos Administrativos"),
            "ip_bra": ("Seguro de Viaje Gratis, Kilometros Ilimitados, "
                       "Modificaciones Flexibles y Beneficio en Cobertura del IOF"),
        }
        benef = beneficios_map.get(campo, "")
        return (
            f"¡Ahorra hasta el 35% en tu alquiler de autos en {ubicacion} "
            f"con Miles Car Rental! Elige entre compactos, SUVs, vans, "
            f"convertibles y autos de lujo. Obtienes: {benef}. "
            f"Con mas de 15 anos de trayectoria y alianzas con las mejores "
            f"agencias. Selecciona tus fechas y vive tu proximo viaje sin "
            f"preocupaciones."
        )

    def _fleet_fill_individual(self, fields, missing, ubicacion, tit, brand='mcr'):
        """Genera individualmente cada campo faltante de fleet/sectionCars."""
        if brand == 'mcr':
            beneficios = {
                'desc': (
                    "Seguro de Viaje Gratis, Kilómetros Ilimitados, "
                    "Asistencia Básica en Carretera, Modificaciones Flexibles"
                ),
                'ip_usa': (
                    "Kilómetros Ilimitados, Asistencia Básica en Carretera, "
                    "Modificaciones sin cargos administrativos "
                    "(NO incluye Seguro de Viaje Gratis)"
                ),
                'ip_bra': (
                    "Seguro de Viaje Gratis, Kilómetros Ilimitados, "
                    "Modificaciones Flexibles, Beneficio en Cobertura del IOF"
                ),
            }
        else:
            beneficios = {
                'desc': (
                    "Seguro de Viaje Gratis, Kilómetros Ilimitados, "
                    "Conductor Adicional sin costo extra, Modificaciones Flexibles"
                ),
                'ip_usa': (
                    "Kilómetros Ilimitados, Asistencia Básica en Carretera, "
                    "Modificaciones sin cargos administrativos "
                    "(NO incluye Seguro de Viaje Gratis ni Conductor Adicional)"
                ),
                'ip_bra': (
                    "Seguro de Viaje Gratis, Kilómetros Ilimitados, "
                    "Modificaciones Flexibles, Beneficio en Cobertura del IOF"
                ),
            }
        audiencia = {
            'desc': 'viajeros latinoamericanos y extranjeros visitando el destino',
            'ip_usa': 'residentes de Estados Unidos que rentan localmente',
            'ip_bra': 'residentes de Brasil visitando el destino',
        }
        marca = "Miles Car Rental" if brand == 'mcr' else "Viajemos"
        palabras = "125 a 130" if brand == 'mcr' else "80 a 85"
        sys_prompt = self.system_seo if brand == 'mcr' else SYSTEM_VJM
        for campo in missing:
            # Restricciones especificas por campo
            restr = ""
            if campo == "desc":
                restr = (
                    "RESTRICCIONES CRITICAS para 'desc' (LATAM):\n"
                    "- NO menciones 'IOF' ni 'Cobertura del IOF' (ese beneficio "
                    "SOLO es para residentes de Brasil, va en ip_bra).\n"
                    "- NO menciones 'Conductor Adicional' (es para Viajemos).\n"
                )
            elif campo == "ip_usa":
                restr = (
                    "RESTRICCIONES CRITICAS para 'ip_usa' (residentes USA):\n"
                    "- NO menciones 'Seguro de Viaje Gratis' (no aplica para residentes USA).\n"
                    "- NO menciones 'IOF'.\n"
                )
            elif campo == "ip_bra":
                restr = (
                    "RESTRICCIONES para 'ip_bra' (residentes Brasil):\n"
                    "- SI menciona 'Beneficio en Cobertura del IOF'.\n"
                )
            prompt_ind = (
                f"Redacta UN texto de {palabras} palabras sobre renta de autos en {ubicacion} "
                f"para {marca}, dirigido a {audiencia[campo]}.\n\n"
                f"El texto debe:\n"
                f"1. Apertura original invitando a explorar ofertas, "
                f"mencionar descuentos hasta del 35%%, variedad de vehiculos.\n"
                f"2. Beneficios EXACTOS (NO agregues otros): {beneficios[campo]}\n"
                f"3. Cierre: trayectoria de mas de 15 anos, alianzas con agencias, "
                f"invitar a seleccionar fechas.\n\n"
                f"{restr}\n"
                f"FORMATO CRITICO:\n"
                f"- Texto continuo en un SOLO parrafo, sin saltos de linea extra.\n"
                f"- Capitalizacion NORMAL de oracion: solo la primera letra de cada "
                f"oracion en mayuscula y nombres propios. NUNCA escribas palabras "
                f"enteras en MAYUSCULAS (excepto siglas como USA, IOF, GA, TN).\n\n"
                f"Genera SOLO:\n|{campo}: tu texto completo|"
            )
            min_words = 70 if brand == 'mcr' else 50
            # 4 intentos con tokens altos + temperatura mas baja para estabilidad
            for attempt in range(4):
                raw = self._call(sys_prompt, prompt_ind,
                                 temperature=0.5, max_tokens=4000)
                parsed = self.parse_fields(raw)
                val = parsed.get(campo, '')
                if val and len(val.split()) >= min_words:
                    fields[campo] = self._clean_fleet_text(val, campo)
                    log.info("fleet %s: campo '%s' OK en intento %d",
                             brand, campo, attempt + 1)
                    break
                # Si no se parseo con pipe, tomar el texto crudo completo
                cleaned = raw.strip()
                cleaned = re.sub(r'^\|\s*\w+\s*:\s*', '', cleaned)
                cleaned = re.sub(r'\s*\|$', '', cleaned)
                if cleaned and len(cleaned.split()) >= min_words:
                    fields[campo] = self._clean_fleet_text(cleaned, campo)
                    log.info("fleet %s: campo '%s' desde texto crudo (intento %d)",
                             brand, campo, attempt + 1)
                    break
                log.warning("fleet %s: campo '%s' intento %d/4 fallo (palabras=%d)",
                            brand, campo, attempt + 1,
                            len(val.split()) if val else 0)

    @staticmethod
    def _clean_fleet_text(text: str, campo: str) -> str:
        """Limpia texto de fleet: normaliza saltos y remueve beneficios cruzados."""
        if not text:
            return text
        t = LMClient._strip_banned(text)
        # Para desc LATAM: remover menciones de IOF (solo va en ip_bra)
        if campo == "desc":
            t = re.sub(r",?\s*(y\s+)?(Beneficio\s+en\s+)?Cobertura\s+(del\s+)?IOF\b", "", t, flags=re.IGNORECASE)
            t = re.sub(r",?\s*IOF\b", "", t)
        # Para ip_usa: remover Seguro de Viaje Gratis
        if campo == "ip_usa":
            t = re.sub(r",?\s*(y\s+)?Seguro\s+de\s+Viaje\s+Gratis", "", t, flags=re.IGNORECASE)
            t = re.sub(r",?\s*(y\s+)?Cobertura\s+de\s+Viaje\s+Gratis", "", t, flags=re.IGNORECASE)
        # Normalizar saltos de linea
        t = re.sub(r'\n{3,}', '\n\n', t)
        t = t.replace('\u202f', ' ').replace('\u00a0', ' ')
        t = re.sub(r'  +', ' ', t)
        # Arreglar comas sueltas tras remover
        t = re.sub(r',\s*,', ',', t)
        t = re.sub(r',\s*\.', '.', t)
        t = re.sub(r'\s+,', ',', t)
        return t.strip()

    @staticmethod
    def _normalize_uppercase(text: str) -> str:
        """Detecta texto con ALL CAPS excesivo y lo convierte a formato oracion.

        Si hay una secuencia de >= 3 palabras consecutivas todas en MAYUSCULAS
        (excepto siglas: USA, IOF, GA, TN, NY, CA, FL, TX, PR, MX, BR, etc.),
        convierte ese fragmento a lowercase y capitaliza la primera letra
        de cada oracion.
        """
        if not text:
            return text
        siglas_explicit = {
            "USA", "IOF", "VJM", "MCR", "SUV", "GPS", "USD",
            "GA", "TN", "NY", "CA", "FL", "TX", "AZ", "NV", "NC", "MA", "MI",
            "LA", "SF", "LV", "PR", "MX", "BR", "AR", "CL", "PE", "CO",
            "I-10", "I-20", "I-40", "I-95", "OK", "DC", "WA", "OR",
            "NJ", "PA", "OH", "IL", "WI", "MN", "MO", "KS", "KY",
        }

        def normalize_upper_segment(match):
            segment = match.group(0)
            tokens = segment.split(' ')
            out = []
            for tok in tokens:
                clean = re.sub(r'[^\w]', '', tok)
                if clean.upper() in siglas_explicit:
                    out.append(tok)
                else:
                    out.append(tok.lower())
            joined = ' '.join(out)
            return joined[:1].upper() + joined[1:] if joined else joined

        # Patron: >= 3 palabras de >= 2 letras en MAYUSCULAS, separadas por espacios
        pattern = r'(?:[A-ZÁÉÍÓÚÑÜ]{2,}[\.,;:!?]?\s+){2,}[A-ZÁÉÍÓÚÑÜ]{2,}[\.,;:!?]?'
        normalized = re.sub(pattern, normalize_upper_segment, text)

        # Pasada extra: palabras MAYUSCULAS aisladas (artefactos del primer pase)
        # como "Y CULTURAL", "LA" que quedaron solas tras la normalizacion
        def normalize_isolated_upper(m):
            word = m.group(0)
            clean = re.sub(r'[^\w]', '', word)
            if clean.upper() in siglas_explicit:
                return word
            return word.lower()
        # Solo palabras de 2+ letras que estan rodeadas por minusculas/espacios
        normalized = re.sub(
            r'(?<=[a-z\s])([A-ZÁÉÍÓÚÑÜ]{2,})(?=[\s\.\,;:!?])',
            normalize_isolated_upper,
            normalized
        )

        # Capitalizar inicio de cada oracion
        normalized = re.sub(
            r'(^|[\.!?]\s+)([a-záéíóúñü])',
            lambda m: m.group(1) + m.group(2).upper(),
            normalized
        )
        return normalized

    @staticmethod
    def _strip_banned(text: str) -> str:
        """Remueve frases/beneficios prohibidos de cualquier texto generado.

        Banned: cargos ocultos, seguro contra accidentes, asistencia premium,
        GPS gratis, furgonetas, descuentos relámpago.
        NOTA: 'alianzas con agencias' es VALIDO (ambos MCR y VJM son comparadores).
        Ademas normaliza texto ALL-CAPS excesivo.
        """
        if not text:
            return text
        t = LMClient._normalize_uppercase(text)
        banned_patterns = [
            # 'sin cargos ocultos', 'sin gastos ocultos', etc.
            (r",?\s*(sin|con)\s+(cargos|gastos|pagos|costos)\s+ocultos\.?", "."),
            (r",?\s*todo\s+sin\s+(cargos|gastos|pagos|costos)\s+ocultos\.?", "."),
            (r",?\s*(cargos|gastos|pagos|costos)\s+ocultos", ""),
            (r",?\s*sin\s+sorpresas", ""),
            (r",?\s*descuentos\s+relampago|descuentos\s+relámpago", ""),
            # Beneficios inventados (no están en tabla oficial)
            (r",?\s*(y\s+)?seguro\s+(de\s+)?protecci[oó]n\s+contra\s+accidentes", ""),
            (r",?\s*(y\s+)?asistencia\s+premium", ""),
            (r",?\s*(y\s+)?GPS\s+gratis", ""),
            # furgonetas -> vans
            (r"\bfurgonetas?\b", "vans"),
            (r"\bFurgonetas?\b", "Vans"),
            # SUVs -> SUV (nunca con s)
            (r"\bSUVs\b", "SUV"),
            # "autos tipo SUV" -> "SUV" (artificial)
            (r"\bautos\s+tipo\s+SUV\b", "SUV"),
            (r"\bautos\s+tipo\s+[Vv]an\b", "Van"),
            (r"\bcarros\s+tipo\s+SUV\b", "SUV"),
            (r"\bcarros\s+tipo\s+[Vv]an\b", "Van"),
        ]
        for pat, rep in banned_patterns:
            t = re.sub(pat, rep, t, flags=re.IGNORECASE)
        # Porcentajes sin espacio: "35 %" -> "35%"
        t = re.sub(r'(\d+)\s+%', r'\1%', t)
        # Arreglar comas/espacios tras remoción
        t = re.sub(r',\s*,', ',', t)
        t = re.sub(r',\s*\.', '.', t)
        t = re.sub(r'\s+,', ',', t)
        t = re.sub(r'\.\s*\.', '.', t)
        t = re.sub(r'  +', ' ', t)
        return t.strip()

    def generate_reviews(self, ciudad: str, estado: str = "",
                         tit: str = "") -> dict:
        """B4: reviews — H2 + desc 35-40 palabras."""
        if not tit:
            tit = f"Opiniones sobre alquiler de vehículos en {ciudad}"
        ubicacion = f"{ciudad}, {estado}" if estado else ciudad

        prompt = (
            "Ejemplo de referencia:\n"
            "'¡Que no queden dudas! Somos los No. 1 en alquiler de autos en "
            "Memphis, Tennessee. Los comentarios de miles de usuarios satisfechos "
            "y nuestra calificación de 4.8/5 lo demuestran. Deja tus recorridos "
            "en manos expertas y reserva con nosotros.'\n\n"
            f"Nuevo tema: {ubicacion}\n"
            "Reglas para desc: EXACTAMENTE 35 a 40 palabras.\n"
            "Tono: exclamativo y directo. Menciona 'No. 1', 'miles de usuarios "
            "satisfechos', calificación 4.8/5 y cierra invitando a reservar. "
            "NO menciones porcentaje de descuento en este bloque.\n"
            "CRITICO: Siempre debes usar la KW 'alquiler de autos' o sinonimo "
            "('renta de autos', 'alquiler de carros', 'alquiler de vehiculos'). "
            "Si el tema es un tipo de auto (ej. convertibles), escribe "
            "'alquiler de autos convertibles', NUNCA 'alquiler de convertibles'.\n\n"
            "Genera:\n"
            f"|tit: {tit}|\n"
            "|desc: redacción|"
        )
        raw = self._call(self.system_seo, prompt, max_tokens=2000)
        fields = self.parse_fields(raw)
        if "tit" not in fields:
            fields["tit"] = tit
        # Garantizar desc no vacia + supervisar
        if not fields.get("desc") or len(fields.get("desc", "").split()) < 10:
            fields["desc"] = self._generate_field(
                prompt, "desc", system=self.system_seo, max_tokens=2000,
                min_words=20,
            )
        return self.supervise_fields(fields, required_keys=["desc"],
                                     min_words=20, prompt_ctx=prompt)

    def generate_rentcompanies(self, ciudad: str, estado: str = "",
                               tit: str = "") -> dict:
        """B5: rentcompanies — H2 + desc 80-85 palabras."""
        if not tit:
            tit = f"Agencias de renta de carros en {ciudad}"
            if estado:
                tit += f", {estado}"
        ubicacion = f"{ciudad}, {estado}" if estado else ciudad

        prompt = (
            f"Nuevo tema: {ubicacion}\n"
            "Reglas para desc: EXACTAMENTE 80 a 85 palabras.\n"
            "Contexto: El usuario puede comparar precios de distintas agencias "
            "asociadas prestigiosas en un solo lugar. Menciona facilidad de "
            "comparación, variedad de opciones y respaldo de agencias reconocidas.\n\n"
            "Genera:\n"
            f"|tit: {tit}|\n"
            "|desc: redacción|"
        )
        raw = self._call(self.system_seo, prompt, max_tokens=2000)
        fields = self.parse_fields(raw)
        if "tit" not in fields:
            fields["tit"] = tit
        if not fields.get("desc") or len(fields.get("desc", "").split()) < 30:
            fields["desc"] = self._generate_field(
                prompt, "desc", system=self.system_seo, max_tokens=2000,
                min_words=40,
            )
        return self.supervise_fields(fields, required_keys=["desc"],
                                     min_words=40, prompt_ctx=prompt)

    def generate_questions_header(self, ciudad: str, estado: str = "",
                                  tit: str = "") -> dict:
        """B3: questions header — H2 + desc 40-45 palabras."""
        if not tit:
            tit = f"Preguntas frecuentes sobre Alquiler de Autos en {ciudad}"
        ubicacion = f"{ciudad}, {estado}" if estado else ciudad

        prompt = (
            "Ejemplo de referencia:\n"
            "'¡Las dudas no caben en el auto! Encuentra aquí las respuestas "
            "que buscas a tus preguntas frecuentes sobre alquiler de carros en "
            "Memphis, Tennessee. Conoce información esencial acerca de las "
            "diferentes tarifas, agencias destacadas y requisitos de renta "
            "para que reserves con total tranquilidad.'\n\n"
            f"Nuevo tema: {ubicacion}\n"
            "Reglas para desc: EXACTAMENTE 40 a 45 palabras.\n"
            "Tono: entusiasta y directo. Abre con una frase impactante. "
            "Menciona que aquí encontrarán respuestas sobre tarifas, agencias "
            "y requisitos. Cierra invitando a reservar con tranquilidad.\n\n"
            "Genera:\n"
            f"|tit: {tit}|\n"
            "|desc: redacción introductoria a las FAQs|"
        )
        raw = self._call(self.system_seo, prompt, max_tokens=2000)
        fields = self.parse_fields(raw)
        if "tit" not in fields:
            fields["tit"] = tit
        if not fields.get("desc") or len(fields.get("desc", "").split()) < 25:
            fields["desc"] = self._generate_field(
                prompt, "desc", system=self.system_seo, max_tokens=2000,
                min_words=25,
            )
        return self.supervise_fields(fields, required_keys=["desc"],
                                     min_words=25, prompt_ctx=prompt)

    def generate_faq_answers(self, ciudad: str, estado: str = "",
                             estado_abrev: str = "",
                             precio_dia: str = "9",
                             precio_semana: str = "63",
                             agencias_precios: Optional[list] = None) -> dict:
        """B3b: respuestas FAQ — templates estandarizados.

        Las FAQs siguen una estructura muy fija; solo varían ciudad/estado
        y datos de precio. Se generan como templates con párrafos de cierre
        ligeramente parafraseados por el LLM.

        estado_abrev: código postal del estado (ej: "TN" para Tennessee).
        Si no se pasa, se usa estado completo.
        """
        ub = f"{ciudad}, {estado}" if estado else ciudad
        abrev = estado_abrev or (estado if estado else "")
        ub_corto = f"{ciudad}, {abrev}" if abrev else ciudad

        if not agencias_precios:
            agencias_precios = [
                ("Alamo", precio_dia),
                ("Dollar", str(int(precio_dia) + 1)),
                ("Avis", str(int(precio_dia) + 2)),
            ]

        # FAQ 1: ¿Cuánto cuesta rentar? — template fijo
        faq_1 = (
            f"Alquilar un auto en {ub_corto} tiene un costo que va desde los "
            f"USD ${precio_dia} al día, a través de {self.brand_name}.\n\n"
            f"Ten en cuenta que esta tarifa puede variar de acuerdo con el tipo "
            f"de vehículo seleccionado, la compañía de alquiler, la temporada de "
            f"viaje y los servicios adicionales que agregues en la reserva."
        )

        # FAQ 2: ¿Qué se necesita? — template fijo con lista de requisitos
        faq_2 = (
            f"Los requisitos para rentar un carro en {ub} son:\n"
            "**\n"
            "- Tener mínimo 25 años.*\n"
            "- Licencia de conducción física de tu país de origen con fecha de "
            "expedición mayor a 1 año y nombre impreso.\n"
            "- Pasaporte vigente.\n"  # No usar \u00a0 aqui
            "- Tarjeta de crédito a nombre del titular que hace la reserva, "
            "con cupo suficiente para cubrir el depósito de alquiler.\n"
            "- Depósito de garantía.\n"
            "- Voucher impreso para comprobar que la reserva fue prepagada, "
            "en caso de que seas extranjero.\n"
            "- Tiquetes aéreos de ida y vuelta.\n"
            "**\n"
            "*Algunas compañías de renta aceptan que el titular de la reserva "
            "sea menor de 25 años (21 a 24) pagando un recargo adicional en el "
            "mostrador.\n\n"
            "No olvides que es necesario presentar todos los documentos en "
            "formato físico al momento de recoger el vehículo en la agencia. "
            "Es posible que algunos requisitos cambien según tu país de origen, "
            "por eso te invitamos a consultar todos los detalles con Emma, "
            "nuestro Chatbot."
        )

        # FAQ 3: ¿Cuál es la agencia más barata? — template con lista de agencias
        agencias_lines = "\n".join(
            f"- {ag}, desde USD ${pr}/día" for ag, pr in agencias_precios
        )
        faq_3 = (
            f"Las compañías de renta de vehículos con las tarifas más económicas "
            f"en {ub} son:\n"
            "**\n"
            f"{agencias_lines}\n"
            "**\n"
            "En nuestro portal web puedes comparar los precios de estas y otras "
            "agencias para que elijas la de tu preferencia. No olvides que este "
            "costo puede cambiar de acuerdo con la empresa de alquiler, la "
            "temporada de viaje, la categoría del vehículo y los servicios "
            "adicionales añadidos a tu reserva.\n"
            "¡Selecciona las fechas de tu itinerario ahora mismo y accede a "
            "ofertas imperdibles!"
        )

        # FAQ 4: ¿Cuánto cuesta por una semana? — template fijo
        faq_4 = (
            f"Alquilar un carro durante una semana en {ub} tiene un costo "
            f"desde los USD ${precio_semana}.\n\n"
            "Recuerda que este precio puede cambiar según la temporada, la "
            "agencia elegida, el tipo de vehículo y los servicios adicionales "
            "incluidos en la reserva."
        )

        return {
            "faq_1": faq_1,
            "faq_2": faq_2,
            "faq_3": faq_3,
            "faq_4": faq_4,
        }

    def generate_faq_questions(self, ciudad: str, estado: str = "",
                               estado_abrev: str = "") -> dict:
        """Genera las 4 preguntas FAQ estándar (fijas)."""
        ub = f"{ciudad}, {estado}" if estado else ciudad
        abrev = estado_abrev or (estado if estado else "")
        ub_corto = f"{ciudad}, {abrev}" if abrev else ciudad
        return {
            "q_1": f"¿Cuánto cuesta rentar un auto en {ub}?",
            "q_2": f"¿Qué se necesita para alquilar un coche en {ub_corto}?",
            "q_3": f"¿Cuál es la agencia de alquiler de autos con los precios más baratos en {ub_corto}?",
            "q_4": f"¿Cuánto cuesta rentar un carro por una semana en {ciudad}?",
        }

    def generate_advicestipocarrusel(self, ciudad: str, estado: str = "",
                                     tit: str = "",
                                     topics: Optional[list] = None) -> dict:
        """B6: advicestipocarrusel (Consejos) — H2 60-65p + clusters 30-80p."""
        if not tit:
            tit = f"Consejos para rentar un auto en {ciudad}"
        if not topics:
            topics = [
                f"Seguro de auto al rentar en {ciudad}",
                f"Documentos necesarios para alquilar en {ciudad}",
                f"Mejores temporadas para visitar {ciudad}",
                f"Consejos de tráfico y estacionamiento en {ciudad}",
                f"Devolución del vehículo en {ciudad}",
            ]
        ubicacion = f"{ciudad}, {estado}" if estado else ciudad

        topics_text = "\n".join(f"{i+1}. {t}" for i, t in enumerate(topics))
        prompt = (
            f"Nuevo tema: {ubicacion}\n"
            "Primero genera H2 y su descripción (EXACTAMENTE 60-65 palabras).\n"
            f"Luego genera una descripción para cada consejo "
            f"(entre 30 y 80 palabras cada uno):\n{topics_text}\n\n"
            "Estructura:\n"
            f"|tit: {tit}|\n"
            "|desc: descripción H2|\n"
            + "\n".join(f"|desc_{i+1}: consejo sobre {t}|"
                        for i, t in enumerate(topics))
        )
        raw = self._call(self.system_seo, prompt, max_tokens=4000)
        fields = self.parse_fields(raw)
        if "tit" not in fields:
            fields["tit"] = tit
        return fields

    def generate_fleetcarrusel(self, ciudad: str, estado: str = "",
                               estado_abrev: str = "",
                               tit: str = "",
                               car_types: Optional[list] = None,
                               skip_type: str = "") -> dict:
        """B7: fleetcarrusel — H2 80-85p (LLM) + H3 15-20p (templates).

        H3 son templates estandarizados con frase motivacional + acción + ciudad.
        Orden fijo: Económicos, Camionetas, Vans, Convertibles, Lujo, Eléctricos.
        skip_type: si la LP es de un tipo_auto, se omite ese tipo del carrusel.
        """
        abrev = estado_abrev or (estado[:2].upper() if estado else "")
        ub_corto = f"{ciudad}, {abrev}" if abrev else ciudad
        ubicacion = f"{ciudad}, {estado}" if estado else ciudad

        if not tit:
            tit = f"Amplia variedad de vehículos para rentar en {ub_corto}"
        if not car_types:
            car_types = [
                "Carros Económicos", "Camionetas", "Vans",
                "Convertibles", "Carros de Lujo", "Carros Eléctricos",
            ]
        # Para LP tipo_auto: omitir el tipo que corresponde a la LP
        if skip_type:
            car_types = [ct for ct in car_types if skip_type.lower() not in ct.lower()]

        # ── H3 templates fijos por tipo de auto ──
        _templates_h3 = {
            "Carros Económicos": (
                f"¡Viaja más mientras pagas menos! Renta un auto económico en "
                f"{ub_corto} al precio más bajo del mercado."
            ),
            "Camionetas": (
                f"Alquiler de SUV en {ubicacion}: siente la tranquilidad de "
                f"viajar con tracción superior y máximo espacio."
            ),
            "Vans": (
                f"¡Que nadie se quede atrás! Renta una Van en {ciudad} "
                f"y recorre {estado or 'cada destino'} junto a todos tus amigos."
            ),
            "Convertibles": (
                f"Alquiler de autos convertibles en {ciudad}: domina las calles "
                f"de {estado or 'la ciudad'} con estilo superior."
            ),
            "Carros de Lujo": (
                f"¡Deja que tu elegancia deslumbre en la carretera! Renta un "
                f"auto de lujo en {ub_corto} con {self.brand_name}."
            ),
            "Carros Eléctricos": (
                f"¡Conduce el futuro hoy! Alquiler de autos eléctricos en "
                f"{ub_corto}: recorre la ciudad con cero emisiones."
            ),
        }

        # ── H2 desc se genera con LLM (80-85 palabras) ──
        prompt = (
            "Ejemplo de referencia:\n"
            "'¡Cada aventura merece un vehículo especial! Encuentra el tuyo "
            "con nosotros. Te damos acceso a una completa selección de autos "
            "de alquiler en Memphis, Tennessee. Compara características y reserva "
            "tu favorito en cuestión de minutos. Elige desde carros compactos, "
            "pequeños en tamaño y grandes en rendimiento, hasta amplias vans con "
            "espacio para todos. También puedes optar por SUVs espaciosas, "
            "descapotables con mucho estilo o magníficos autos de lujo que se "
            "robarán todas las miradas en carretera. ¡Haz tu viaje a tu manera!'\n\n"
            f"Nuevo tema: {ubicacion}\n"
            "Reglas para desc: EXACTAMENTE 80 a 85 palabras.\n"
            "Menciona la variedad de tipos de auto disponibles. "
            "Tono entusiasta, incluye llamada a la acción.\n\n"
            "Genera SOLO el H2:\n"
            f"|tit: {tit}|\n"
            "|desc: descripción H2|"
        )
        raw = self._call(self.system_seo, prompt, max_tokens=2000)
        fields = self.parse_fields(raw)
        if "tit" not in fields:
            fields["tit"] = tit

        # Garantizar desc no vacio con retry + fallback
        if not fields.get("desc") or len(fields.get("desc", "").split()) < 40:
            fields["desc"] = self._generate_field(
                prompt, "desc", system=self.system_seo, max_tokens=2000,
                min_words=40,
            )

        # Agregar H3 templates
        for i, ct in enumerate(car_types):
            key = f"desc_{i+1}"
            fields[key] = _templates_h3.get(ct, f"Renta un {ct.lower()} en {ub_corto} con las mejores tarifas del mercado.")

        return self.supervise_fields(fields, required_keys=["desc"],
                                     min_words=40, prompt_ctx=prompt)

    def generate_locationscarrusel(self, ciudad: str, estado: str = "",
                                   tit: str = "",
                                   locations: Optional[list] = None,
                                   tipo_lp: str = "ciudad") -> dict:
        """B8: locationscarrusel MCR — H2 75-80p (LLM) + 17 ciudades estándar con desc.

        Si se pasan locations explícitas (localidades de BD), se usan esas.
        Sino, usa las 17 ciudades estándar (Miami→Austin) con desc comercial.
        """
        ubicacion = f"{ciudad}, {estado}" if estado else ciudad

        if not tit:
            tit = "Renta de autos en otras ciudades de USA"

        # ── H3: 17 ciudades estándar con desc comercial (o localidades de BD) ──
        h3_fields = {}
        if locations:
            # Localidades explícitas de BD
            for i, loc in enumerate(locations):
                if isinstance(loc, tuple):
                    loc_name = loc[0]
                else:
                    loc_name = loc
                h3_fields[f"tit_{i+1}"] = f"Alquiler de autos en {loc_name}"
                h3_fields[f"desc_{i+1}"] = (
                    f"Renta de autos en {loc_name}: aprovecha las mejores tarifas "
                    f"de alquiler de vehiculos con {self.brand_name}. Compara precios "
                    f"de agencias reconocidas y reserva online."
                )
        else:
            # 17 ciudades estándar con desc completo (reutiliza CIUDADES_ESTANDAR_17)
            for i, (name, state, h3_title, desc_text) in enumerate(self.CIUDADES_ESTANDAR_17):
                h3_fields[f"tit_{i+1}"] = h3_title
                h3_fields[f"desc_{i+1}"] = desc_text

        # ── H2 desc se genera con LLM (75-80 palabras) ──
        if locations:
            ctx = (
                f"Contexto: Localidades cercanas a {ciudad}. "
                f"Invita a rentar en localidades cercanas."
            )
        else:
            ctx = (
                f"Contexto: Explorar Estados Unidos con un auto de alquiler. "
                f"{self.brand_name} ofrece hasta el 35% OFF. Menciona ciudades como "
                f"Miami, Los Ángeles, Orlando, Nueva York, Las Vegas. "
                f"Incluye que con Kilómetros Ilimitados pueden viajar entre ciudades."
            )

        prompt = (
            "Ejemplo de referencia:\n"
            "'¡Explora cada rincón de Estados Unidos con un auto de alquiler! "
            "Miles Car Rental no solo te ofrece hasta el 35% OFF en tu tarifa, "
            "también te brinda acceso a cientos de oficinas ubicadas "
            "estratégicamente en los principales destinos del país. Reserva ya "
            "y traza tu ruta por ciudades como Miami, Los Ángeles, Orlando, "
            "Nueva York, Las Vegas y muchas más. Con nuestros Kilómetros "
            "Ilimitados podrás viajar entre ellas con total comodidad, sin que "
            "nada te detenga.'\n\n"
            f"Nuevo tema: {ubicacion}\n"
            "Reglas para desc: EXACTAMENTE 75 a 80 palabras.\n"
            f"{ctx}\n\n"
            "Genera SOLO el H2:\n"
            f"|tit: {tit}|\n"
            "|desc: descripción H2|"
        )
        raw = self._call(self.system_seo, prompt, max_tokens=2000)
        fields = self.parse_fields(raw)
        if "tit" not in fields:
            fields["tit"] = tit

        # Garantizar desc (H2) no vacio
        if not fields.get("desc") or len(fields.get("desc", "").split()) < 40:
            fields["desc"] = self._generate_field(
                prompt, "desc", system=self.system_seo, max_tokens=2000,
                min_words=40,
            )

        # Agregar H3 templates
        fields.update(h3_fields)
        return self.supervise_fields(fields, required_keys=["desc"],
                                     min_words=40, prompt_ctx=prompt)

    def generate_rentacar(self, ciudad: str, estado: str = "",
                          tit: str = "", tipo_lp: str = "ciudad",
                          agencia: str = "", tipo_auto: str = "",
                          localidad: str = "") -> dict:
        """B9: rentacar — mini-blog turístico. Varía según tipo de LP.

        tipo_lp: "ciudad" | "localidad" | "agencia" | "tipo_auto"
        agencia: nombre de la agencia (para tipo_lp="agencia")
        tipo_auto: tipo de vehículo (para tipo_lp="tipo_auto")
        localidad: nombre de localidad/aeropuerto (para tipo_lp="localidad")
        """
        ubicacion = f"{ciudad}, {estado}" if estado else ciudad
        loc = localidad or ciudad

        if tipo_lp == "ciudad":
            return self._rentacar_ciudad(ciudad, estado, ubicacion, tit)
        elif tipo_lp == "localidad":
            return self._rentacar_localidad(loc, ciudad, estado, ubicacion, tit)
        elif tipo_lp == "agencia":
            return self._rentacar_agencia(agencia, ciudad, estado, ubicacion, tit)
        elif tipo_lp == "tipo_auto":
            return self._rentacar_tipo_auto(tipo_auto, ciudad, estado, ubicacion, tit)
        else:
            return self._rentacar_ciudad(ciudad, estado, ubicacion, tit)

    def _rentacar_ciudad(self, ciudad, estado, ubicacion, tit=""):
        """Rentacar CIUDAD: lugares + actividades gratis + 3 días.
        Se genera en 3 llamadas separadas para mayor confiabilidad.
        """
        if not tit:
            tit = f"Mejores lugares para visitar en {ciudad}"

        fields = {"tit": tit}

        # ── Llamada 1: desc (lugares turísticos 100-130p) ──
        p1 = (
            f"Escribe un texto de 100-130 palabras con los mejores lugares "
            f"turísticos de {ubicacion}.\n\n"
            f"FORMATO OBLIGATORIO (respeta saltos de línea):\n"
            f"Parrafo introductorio de 2-3 frases.\n"
            f"**\n"
            f"- Lugar 1: descripcion breve.\n"
            f"- Lugar 2: descripcion breve.\n"
            f"- Lugar 3: descripcion breve.\n"
            f"- Lugar 4: descripcion breve.\n"
            f"**\n"
            f"Frase de cierre invitando a rentar un auto para recorrerlos.\n\n"
            f"Reglas:\n"
            f"- Abre con 'Si quieres conocer los mejores lugares para "
            f"visitar en {ciudad}, renta tu auto...'\n"
            f"- Incluye 3 a 6 items en la lista.\n"
            f"- Cada item en linea propia iniciando con '- '.\n"
            f"- Envuelve la lista con '**' en lineas propias (arriba y abajo).\n"
            f"- Usa siempre 'alquiler de autos' o sinonimo, nunca el tipo aislado.\n\n"
            f"|desc: tu redacción completa con saltos de linea|"
        )
        fields["desc"] = self._generate_field(p1, "desc", max_tokens=2000)

        # ── Llamada 2: desc_1 (actividades gratis 220-250p) ──
        fields["tit_1"] = f"Actividades gratis para hacer en {ciudad}"
        p2 = (
            f"Redacta un articulo de 220 a 250 palabras sobre actividades "
            f"gratuitas en {ubicacion}. Abre con frase atractiva tipo "
            f"'Quien dijo que necesitas gastar mucho para disfrutar de una ciudad?'.\n\n"
            f"FORMATO OBLIGATORIO:\n"
            f"Parrafo introductorio.\n"
            f"*h4 Titulo actividad 1 *h4\n"
            f"Descripcion de la actividad 1.\n"
            f"*h4 Titulo actividad 2 *h4\n"
            f"Descripcion de la actividad 2.\n"
            f"(repetir para 5 actividades totales)\n"
            f"Frase final de cierre.\n\n"
            f"|desc_1: tu redacción completa|"
        )
        fields["desc_1"] = self._generate_field(p2, "desc_1")

        # ── Llamada 3: desc_2 (3 días 220-250p) ──
        fields["tit_2"] = f"¿Qué hacer en 3 días en {ciudad}?"
        p3 = (
            f"Redacta un articulo de 220 a 250 palabras con un itinerario de "
            f"3 dias en {ubicacion}. Abre con frase tipo 'Planeas visitar esta "
            f"ciudad iconica?'.\n\n"
            f"FORMATO OBLIGATORIO (respeta saltos de linea):\n"
            f"Parrafo introductorio.\n"
            f"*h4 Dia 1: titulo tematico *h4\n"
            f"**\n"
            f"- Actividad 1 del dia\n"
            f"- Actividad 2 del dia\n"
            f"- Actividad 3 del dia\n"
            f"**\n"
            f"*h4 Dia 2: titulo tematico *h4\n"
            f"**\n"
            f"- Actividad 1 del dia\n"
            f"- Actividad 2 del dia\n"
            f"**\n"
            f"*h4 Dia 3: titulo tematico *h4\n"
            f"**\n"
            f"- Actividad 1 del dia\n"
            f"- Actividad 2 del dia\n"
            f"**\n"
            f"Frase de cierre.\n\n"
            f"Cada item en linea propia con '- '. La lista envuelta en '**'.\n\n"
            f"|desc_2: tu redacción completa|"
        )
        fields["desc_2"] = self._generate_field(
            p3, "desc_2", max_tokens=6000, min_words=180, retries=4
        )

        return fields

    def _rentacar_localidad(self, localidad, ciudad, estado, ubicacion, tit=""):
        """Rentacar LOCALIDAD: lugares cerca + transporte + atracción.
        Se genera en 3 llamadas separadas para mayor confiabilidad.
        """
        if not tit:
            tit = f"Lugares para visitar cerca del {localidad}"

        fields = {"tit": tit}

        # ── Llamada 1: desc (lugares cercanos 100-135p) ──
        p1 = (
            f"Escribe un texto de 100-135 palabras sobre los mejores lugares "
            f"para visitar cerca del {localidad} en {ubicacion}.\n\n"
            f"FORMATO OBLIGATORIO (respeta saltos de linea):\n"
            f"Parrafo introductorio de 2-3 frases.\n"
            f"**\n"
            f"- Lugar 1: descripcion breve + distancia.\n"
            f"- Lugar 2: descripcion breve + distancia.\n"
            f"- Lugar 3: descripcion breve + distancia.\n"
            f"**\n"
            f"Frase de cierre (invita a rentar auto para recorrerlos).\n\n"
            f"- 3 a 4 items en la lista.\n"
            f"- KW 'alquiler de autos' o sinonimo, no tipo aislado.\n\n"
            f"|desc: tu redacción completa con saltos de linea|"
        )
        fields["desc"] = self._generate_field(p1, "desc", max_tokens=2000)

        # ── Llamada 2: desc_1 (transporte 150-175p) ──
        fields["tit_1"] = f"Mejor opción de transporte desde el {localidad}"
        p2 = (
            f"Redacta un texto de 150-175 palabras explicando por que rentar "
            f"un auto es la mejor opcion de transporte desde el {localidad}. "
            f"Compara con taxi y transporte publico. Menciona variedad de "
            f"vehiculos disponibles, autonomia de horarios y el beneficio "
            f"del alquiler de autos con Miles Car Rental.\n"
            f"KW principal: 'alquiler de autos' / 'renta de autos'.\n\n"
            f"|desc_1: tu redacción completa|"
        )
        fields["desc_1"] = self._generate_field(p2, "desc_1")

        # ── Llamada 3: desc_2 (atracción 220-250p) ──
        p3 = (
            f"Redacta un artículo de 220-250 palabras sobre una atracción "
            f"turística imperdible cerca del {localidad} en {ubicacion}. "
            f"Escribe como un mini-blog: historia, qué se puede hacer, "
            f"eventos, y por qué vale la pena visitarla.\n\n"
            f"|tit_2: título atractivo de la atracción|\n"
            f"|desc_2: tu redacción completa|"
        )
        # Hasta 4 intentos con tokens altos
        desc_2 = ""
        tit_2_fallback = f"Visita las atracciones cerca del {localidad}"
        for attempt in range(4):
            raw3 = self._call(self.system_seo, p3, temperature=0.5, max_tokens=6000)
            f3 = self.parse_fields(raw3)
            candidate_desc = f3.get("desc_2", "").strip()
            candidate_tit = f3.get("tit_2", "").strip()
            if candidate_desc and len(candidate_desc.split()) >= 150:
                desc_2 = candidate_desc
                fields["tit_2"] = candidate_tit or tit_2_fallback
                log.info("desc_2 localidad OK en intento %d", attempt + 1)
                break
            log.warning("desc_2 localidad intento %d/4 insuficiente (palabras=%d)",
                        attempt + 1, len(candidate_desc.split()) if candidate_desc else 0)
        if not desc_2:
            fields["tit_2"] = tit_2_fallback
            desc_2 = self._fallback_text("desc_2", p3)
        fields["desc_2"] = desc_2

        return fields

    def _rentacar_agencia(self, agencia, ciudad, estado, ubicacion, tit=""):
        """Rentacar AGENCIA: oficinas + ubicacion + indicaciones.
        Se genera en 3 llamadas separadas para mayor confiabilidad.
        """
        # Si ciudad incluye el nombre de la agencia (ej. 'Enterprise Atlanta'),
        # quitar el prefijo para obtener solo la ciudad real.
        ciudad_real = ciudad
        if agencia and ciudad.lower().startswith(agencia.lower() + " "):
            ciudad_real = ciudad[len(agencia)+1:].strip()
        ubicacion_real = f"{ciudad_real}, {estado}" if estado else ciudad_real

        if not tit:
            tit = f"¿Cuántas oficinas tiene {agencia} en {ciudad_real}?"

        fields = {"tit": tit}

        # ── Llamada 1: desc (resumen sedes 100-110p) ──
        p1 = (
            f"Escribe un texto de 100-110 palabras resumiendo las sedes de "
            f"{agencia} en {ubicacion_real}. Menciona cercania a aeropuerto, "
            f"variedad de vehiculos disponibles e invita a reservar.\n"
            f"KW principal: 'alquiler de autos' / 'renta de autos'.\n"
            f"Tono directo y conversacional.\n\n"
            f"|desc: tu redaccion completa|"
        )
        fields["desc"] = self._generate_field(p1, "desc", max_tokens=2000, min_words=60)

        # ── Llamada 2: desc_1 (ubicacion 130-145p) ──
        fields["tit_1"] = f"¿Donde estan ubicadas las oficinas de {agencia} en {ciudad_real}?"
        p2 = (
            f"Escribe un texto de 130-145 palabras con la ubicacion detallada "
            f"de la oficina principal de {agencia} en {ciudad_real}. Incluye "
            f"direccion aproximada, como llegar desde el aeropuerto y horarios "
            f"tipicos de atencion.\n\n"
            f"|desc_1: tu redaccion completa|"
        )
        fields["desc_1"] = self._generate_field(p2, "desc_1", max_tokens=2000, min_words=80)

        # ── Llamada 3: desc_2 (indicaciones 220-250p) ──
        fields["tit_2"] = (
            f"Indicaciones para llegar a las principales oficinas de "
            f"{agencia} en {ciudad_real}"
        )
        p3 = (
            f"Escribe un texto de 220-250 palabras con indicaciones paso a "
            f"paso para llegar a las oficinas de {agencia} en {ciudad_real}.\n\n"
            f"FORMATO OBLIGATORIO (respeta saltos de linea):\n"
            f"Parrafo introductorio.\n"
            f"*h4 Paso 1: titulo *h4\n"
            f"Descripcion del paso 1.\n"
            f"*h4 Paso 2: titulo *h4\n"
            f"Descripcion del paso 2.\n"
            f"(repetir hasta 4-5 pasos)\n"
            f"Frase de cierre.\n\n"
            f"|desc_2: tu redaccion completa|"
        )
        fields["desc_2"] = self._generate_field(
            p3, "desc_2", max_tokens=6000, min_words=150, retries=4
        )

        return fields

    def _rentacar_tipo_auto(self, tipo_auto, ciudad, estado, ubicacion, tit=""):
        """Rentacar TIPO_AUTO: atracciones temáticas + nocturno + eventos.

        Se genera en 3 llamadas separadas para evitar que el LLM devuelva
        solo placeholders cuando el prompt es demasiado largo.
        """
        if not tit:
            tit = f"Mejores atracciones de {ciudad}"

        fields = {"tit": tit}

        # ── Llamada 1: desc (atracciones 100-130p) ──
        p1 = (
            f"Escribe un texto de 100-130 palabras sobre las mejores "
            f"atracciones de {ciudad}, {estado}, relacionadolas con el "
            f"alquiler de autos tipo {tipo_auto}.\n\n"
            f"FORMATO OBLIGATORIO (respeta saltos de linea):\n"
            f"Parrafo introductorio de 2-3 frases.\n"
            f"**\n"
            f"- Lugar 1: descripcion breve.\n"
            f"- Lugar 2: descripcion breve.\n"
            f"- Lugar 3: descripcion breve.\n"
            f"- Lugar 4: descripcion breve.\n"
            f"**\n"
            f"Frase de cierre (menciona 'alquiler de autos {tipo_auto.lower()}').\n\n"
            f"Reglas:\n"
            f"- KW principal: 'alquiler de autos {tipo_auto.lower()}' "
            f"(NUNCA 'alquiler de {tipo_auto.lower()}' aislado).\n"
            f"- Cada item en linea propia iniciando con '- '.\n"
            f"- Envuelve la lista con '**' en lineas propias.\n\n"
            f"|desc: tu redacción completa con saltos de linea|"
        )
        fields["desc"] = self._generate_field(p1, "desc", max_tokens=2000)

        # ── Llamada 2: desc_1 (nocturno 190-210p) ──
        fields["tit_1"] = f"¿Qué hacer en {ciudad} de noche?"
        p2 = (
            f"Escribe un texto de 190-210 palabras sobre que hacer en "
            f"{ciudad} de noche.\n\n"
            f"FORMATO OBLIGATORIO (respeta saltos de linea):\n"
            f"Parrafo introductorio.\n"
            f"**\n"
            f"- 1. Plan nocturno 1: descripcion.\n"
            f"- 2. Plan nocturno 2: descripcion.\n"
            f"- 3. Plan nocturno 3: descripcion.\n"
            f"- 4. Plan nocturno 4: descripcion.\n"
            f"- 5. Plan nocturno 5: descripcion.\n"
            f"- 6. Plan nocturno 6: descripcion.\n"
            f"**\n"
            f"Frase de cierre.\n\n"
            f"- Cada item numerado en linea propia con '- N.'.\n"
            f"- Lista envuelta en '**' en lineas propias.\n\n"
            f"|desc_1: tu redacción completa|"
        )
        fields["desc_1"] = self._generate_field(p2, "desc_1")

        # ── Llamada 3: desc_2 (eventos 220-250p) ──
        fields["tit_2"] = f"Mejores eventos en {ciudad}"
        p3 = (
            f"Redacta un artículo de 220 a 250 palabras sobre los mejores "
            f"eventos anuales y actividades culturales en {ciudad}, {estado}.\n"
            f"Organiza el contenido en 4 secciones: Eventos deportivos, "
            f"Celebraciones, Arte y cultura, Música y entretenimiento.\n"
            f"Para cada sección incluye 2 eventos con descripción breve.\n"
            f"Usa formato de viñetas con ** - para listar cada evento.\n\n"
            f"|desc_2: tu redacción completa|"
        )
        fields["desc_2"] = self._generate_field(
            p3, "desc_2", max_tokens=6000, min_words=180, retries=4
        )

        return fields

    # ══════════════════════════════════════════════════════════════════
    # DISCLAIMERS (constantes, nunca se generan con EL LLM)
    # ══════════════════════════════════════════════════════════════════

    DISCLAIMER_PRECIOS = (
        "*Precios basados en los resultados entre los últimos 12 - 24 meses. "
        "Los precios pueden variar de acuerdo a la temporada y disponibilidad."
    )

    DISCLAIMER_FINAL = (
        "*Estos precios son sujetos a cambios y variarán dependiendo de la "
        "temporada del año, el tamaño del vehículo, los días de renta, la "
        "agencia de alquiler de carros, las coberturas que adquieras, entre "
        "otros servicios opcionales."
    )

    # ══════════════════════════════════════════════════════════════════
    # BLOQUES VJM
    # ══════════════════════════════════════════════════════════════════

    def generate_vjm_quicksearch(self, ciudad: str, estado: str = "",
                                 tit: str = "", estado_abrev: str = "") -> dict:
        """VJM B1: quicksearch — H1 + desc 15-20 palabras."""
        abrev = estado_abrev or (estado[:2].upper() if estado else "")
        if not tit:
            ub_tit = f"{ciudad}, {estado}" if estado else ciudad
            tit = f"Renta de autos en {ub_tit} - Mejor Tarifa"
        ubicacion = f"{ciudad}, {estado}" if estado else ciudad

        prompt = (
            "Ejemplos de referencia:\n"
            "Ejemplo 1: tit: Renta de autos en Minneapolis, Minnesota - Mejor Tarifa, "
            "desc: Te damos los precios más bajos en alquiler de carros en Minneapolis. "
            "¡Toma el control de tu aventura al volante!\n"
            "Ejemplo 2: tit: Alquiler de autos en Burbank, California - Mejor Tarifa, "
            "desc: ¡Ahorro garantizado siempre! Comparamos miles de opciones para "
            "brindarte los precios más bajos en renta de carros en Burbank.\n\n"
            f"Nuevo tema: {ubicacion}, tit: {tit}\n"
            "Reglas para desc: EXACTAMENTE 15 a 20 palabras.\n"
            "Contexto: Viajemos es un comparador de precios de renta de autos.\n"
            "Genera:\n"
            f"|tit: {tit}|\n"
            "|desc: tu redacción|"
        )
        raw = self._call(SYSTEM_VJM, prompt, max_tokens=2000)
        fields = self.parse_fields(raw)
        if "tit" not in fields:
            fields["tit"] = tit
        return fields

    # Beneficios por audiencia VJM
    _VJM_BENEFICIOS_LATAM = (
        "Seguro de Viaje Gratis para extranjeros, Kilómetros Ilimitados, "
        "Conductor Adicional sin Costo extra, Modificaciones Flexibles"
    )
    _VJM_BENEFICIOS_USA = (
        "Kilómetros Ilimitados, Asistencia Básica en Carretera, "
        "Modificaciones sin cargos administrativos"
    )
    _VJM_BENEFICIOS_BRA = (
        "Seguro de Viaje Gratis para extranjeros, Kilómetros Ilimitados, "
        "Modificaciones Flexibles, Beneficio en Cobertura del IOF"
    )

    def generate_vjm_sectioncars(self, ciudad: str, estado: str = "",
                                 tit: str = "", estado_abrev: str = "") -> dict:
        """VJM B2: sectionCars — genera 1 texto base (LATAM) y crea USA/BRA
        por reemplazo quirurgico de beneficios. Mismo patron que MCR fleet.
        """
        abrev = estado_abrev or (estado[:2].upper() if estado else "")
        ub_corto = f"{ciudad}, {abrev}" if abrev else ciudad
        if not tit:
            tit = f"Alquiler de carros en {ub_corto}"
        ubicacion = f"{ciudad}, {estado}" if estado else ciudad

        # 1. Generar UN solo texto base con beneficios LATAM VJM
        prompt = (
            f"Redacta UN texto de 80-85 palabras sobre alquiler de autos en "
            f"{ubicacion} para Viajemos (comparador de tarifas).\n\n"
            f"ESTRUCTURA:\n"
            f"Apertura invitando a comparar precios, descuentos, variedad de "
            f"vehiculos. Luego beneficios exclusivos. INCLUYE EXACTAMENTE: "
            f"'{self._VJM_BENEFICIOS_LATAM} y mucho más'. "
            f"Cierre invitando a reservar con Viajemos.\n\n"
            f"IMPORTANTE:\n"
            f"- No empieces con 'Descubre'.\n"
            f"- Los beneficios deben aparecer TEXTUALMENTE.\n\n"
            f"|desc: tu texto completo|"
        )

        desc = self._generate_field(prompt, "desc", system=SYSTEM_VJM,
                                     max_tokens=4000, min_words=50, retries=4,
                                     supervise=False)

        # 2. Crear IP USA y IP BRA por reemplazo
        ip_usa = desc.replace(self._VJM_BENEFICIOS_LATAM, self._VJM_BENEFICIOS_USA)
        ip_bra = desc.replace(self._VJM_BENEFICIOS_LATAM, self._VJM_BENEFICIOS_BRA)

        if ip_usa == desc:
            ip_usa = self._fleet_swap_benefits(desc, "usa")
        if ip_bra == desc:
            ip_bra = self._fleet_swap_benefits(desc, "bra")

        desc = self._clean_fleet_text(desc, "desc")
        ip_usa = self._clean_fleet_text(ip_usa, "ip_usa")
        ip_bra = self._clean_fleet_text(ip_bra, "ip_bra")

        fields = {"tit": tit, "desc": desc, "ip_usa": ip_usa, "ip_bra": ip_bra}
        for k in ("desc", "ip_usa", "ip_bra"):
            if not fields.get(k) or len(fields.get(k, "").split()) < 30:
                fields[k] = self._fleet_template(k, ubicacion)
        return fields

    def generate_vjm_agencies(self, ciudad: str, estado: str = "",
                              tit: str = "", estado_abrev: str = "") -> dict:
        """VJM B3: agencies — H2 60-65p + H3 genérica 28-32p + Disclaimer.

        Solo 1 H3 genérica (no una por agencia). Menciona beneficios de Viajemos.
        """
        abrev = estado_abrev or (estado[:2].upper() if estado else "")
        ub_corto = f"{ciudad}, {abrev}" if abrev else ciudad
        if not tit:
            tit = f"Empresas de alquiler de autos en {ciudad}"
        ubicacion = f"{ciudad}, {estado}" if estado else ciudad

        prompt = (
            "Ejemplo de referencia:\n"
            "H2: 'Con Viajemos, las mejores compañías de alquiler de autos del "
            "mundo te esperan a clics de distancia. Elige tu preferida y renta un "
            "carro en Minneapolis, MN, por el menor precio del mercado. Trabajamos "
            "con empresas destacadas por sus años de experiencia y excelencia "
            "comprobada, como Avis, Budget, Alamo, National y más. Reserva hoy, "
            "nuestras tarifas son tu acceso directo al ahorro.'\n"
            "H3: '¡Disfruta más y paga menos en tus aventuras por las Twin "
            "Cities de Minnesota! Renta un auto con nosotros y disfruta beneficios "
            "exclusivos: Kilómetros Ilimitados, Asistencia Básica en Carretera y "
            "Tarifas Preferenciales.'\n\n"
            f"Nuevo tema: {ubicacion}\n"
            "Reglas:\n"
            "- desc (H2): EXACTAMENTE 60-65 palabras. Menciona que Viajemos "
            "conecta con agencias reconocidas (Avis, Budget, Alamo, National, etc.).\n"
            "- desc_1 (H3 genérica): EXACTAMENTE 28-32 palabras. Frase entusiasta "
            "sobre beneficios: Kilómetros Ilimitados, Asistencia en Carretera, "
            "Tarifas Preferenciales.\n\n"
            "Genera:\n"
            f"|tit: {tit}|\n"
            "|desc: descripción H2|\n"
            "|desc_1: descripción H3 genérica|"
        )
        raw = self._call(SYSTEM_VJM, prompt, max_tokens=4000)
        fields = self.parse_fields(raw)
        if "tit" not in fields:
            fields["tit"] = tit

        # Garantizar desc y desc_1 no vacios
        if not fields.get("desc") or len(fields.get("desc", "").split()) < 20:
            fields["desc"] = self._generate_field(
                prompt, "desc", system=SYSTEM_VJM, max_tokens=4000, min_words=30
            )
        if not fields.get("desc_1") or len(fields.get("desc_1", "").split()) < 10:
            fields["desc_1"] = self._generate_field(
                f"Redacta UNA frase de 28-32 palabras invitando a rentar un auto "
                f"en {ubicacion} con Viajemos. Menciona Kilómetros Ilimitados, "
                f"Asistencia en Carretera y Tarifas Preferenciales.\n\n"
                f"|desc_1: tu frase|",
                "desc_1", system=SYSTEM_VJM, max_tokens=2000, min_words=15
            )
        return fields

    def generate_vjm_rentalcarfaqs_header(self, ciudad: str, estado: str = "",
                                          tit: str = "", estado_abrev: str = "") -> dict:
        """VJM B4a: rentalCarFaqs header — H2 55-60 palabras (LLM)."""
        abrev = estado_abrev or (estado[:2].upper() if estado else "")
        ub_corto = f"{ciudad}, {abrev}" if abrev else ciudad
        if not tit:
            tit = f"Preguntas frecuentes sobre renta de autos en {ub_corto}"
        ubicacion = f"{ciudad}, {estado}" if estado else ciudad

        prompt = (
            "Ejemplo de referencia:\n"
            "'Aquí encontrarás respuestas a tus preguntas más frecuentes sobre "
            "las tarifas, los requisitos y las diferentes agencias de alquiler de "
            "autos en Minneapolis, Minnesota. Eliminamos tus dudas y aumentamos "
            "tu ahorro para que agrandes tus aventuras con el coche ideal para "
            "tu aventura. Deja atrás la incertidumbre y descubre la mejor forma "
            "de viajar por USA con nosotros.'\n\n"
            f"Nuevo tema: {ubicacion}\n"
            "Reglas para desc: EXACTAMENTE 55 a 60 palabras.\n"
            "Menciona tarifas, requisitos y agencias. Cierra invitando a viajar.\n\n"
            "Genera:\n"
            f"|tit: {tit}|\n"
            "|desc: redacción|"
        )
        raw = self._call(SYSTEM_VJM, prompt, max_tokens=2000)
        fields = self.parse_fields(raw)
        if "tit" not in fields:
            fields["tit"] = tit
        return fields

    def generate_vjm_faq_questions(self, ciudad: str, estado: str = "",
                                   estado_abrev: str = "",
                                   aeropuerto: str = "") -> dict:
        """VJM B4b: 4 preguntas FAQ estándar (templates fijos)."""
        ub = f"{ciudad}, {estado}" if estado else ciudad
        abrev = estado_abrev or (estado if estado else "")
        ub_corto = f"{ciudad}, {abrev}" if abrev else ciudad
        aero = aeropuerto or f"Aeropuerto de {ciudad}"
        return {
            "q_1": f"¿Cuánto cuesta alquilar un auto en {ciudad}?",
            "q_2": f"¿Cuál es la mejor compañía de alquiler de carros en {ciudad}?",
            "q_3": f"¿Cuánto cuesta el alquiler de un auto en el {aero}?",
            "q_4": f"¿Qué se necesita para rentar un carro en {ciudad}?",
        }

    def generate_vjm_faq_answers(self, ciudad: str, estado: str = "",
                                 estado_abrev: str = "",
                                 precio_dia: str = "8",
                                 aeropuerto: str = "",
                                 precio_aeropuerto: str = "",
                                 agencias_precios: Optional[list] = None) -> dict:
        """VJM B4c: respuestas FAQ — templates estandarizados.

        Estructura idéntica a MCR pero adaptada a Viajemos como comparador.
        """
        ub = f"{ciudad}, {estado}" if estado else ciudad
        abrev = estado_abrev or (estado if estado else "")
        ub_corto = f"{ciudad}, {abrev}" if abrev else ciudad
        aero = aeropuerto or f"Aeropuerto Internacional de {ciudad}"
        p_aero = precio_aeropuerto or precio_dia

        if not agencias_precios:
            agencias_precios = [
                ("Budget", precio_dia),
                ("Alamo", str(int(precio_dia) + 1)),
                ("Dollar", str(int(precio_dia) + 2)),
                ("Avis", str(int(precio_dia) + 3)),
            ]

        # FAQ 1: ¿Cuánto cuesta?
        faq_1 = (
            f"El precio de renta de carros en {ub_corto} va desde los "
            f"USD ${precio_dia} al día.\n\n"
            f"Esta tarifa puede variar de acuerdo con la temporada de viaje, "
            f"la empresa de alquiler que elijas, el tipo de auto seleccionado "
            f"y los servicios adicionales que agregues a tu reserva."
        )

        # FAQ 2: ¿Cuál es la mejor compañía?
        agencias_lines = "\n".join(
            f"- {ag}, desde USD ${pr}/día." for ag, pr in agencias_precios
        )
        faq_2 = (
            f"Las mejores empresas de renta de autos en {ub_corto} son:\n"
            "**\n"
            f"{agencias_lines}\n"
            "**\n"
            "Ten en cuenta que estas tarifas pueden presentar cambios de acuerdo "
            "con la temporada del año, el tipo de auto seleccionado y los servicios "
            "adicionales incluidos. A través de nuestro website puedes comparar "
            "precios entre estas y más compañías destacadas a nivel mundial. "
            "Elige tu favorita y reserva en minutos."
        )

        # FAQ 3: ¿Cuánto cuesta en el aeropuerto?
        faq_3 = (
            f"La renta de vehículos en el {aero} tiene un costo que va "
            f"desde los USD ${p_aero} al día.\n\n"
            f"Ten presente que este precio puede cambiar según la temporada "
            f"del viaje, la empresa de alquiler elegida, el tipo de auto "
            f"y los servicios adicionales añadidos a tu reserva."
        )

        # FAQ 4: ¿Qué se necesita?
        faq_4 = (
            f"Para rentar un carro en {ub}, necesitas lo siguiente:\n"
            "**\n"
            "- Licencia de conducción física de tu país de origen, vigente, "
            "con expedición superior a un año y con fecha de vencimiento impresa.\n"
            "- Tener mínimo 25 años.*\n"
            "- Tarjeta de crédito del titular de la reserva con su nombre "
            "impreso y cupo suficiente para cubrir el depósito de alquiler.\n"
            "- Depósito de garantía.\n"
            "- Pasaporte vigente.\n"
            "- Voucher que comprueba el pago de la reserva.\n"
            "- Tiquetes aéreos o de crucero (ida y regreso).\n"
            "**\n"
            "*Algunas compañías de alquiler aceptan que el titular de la reserva "
            "sea menor de 25 años (21 a 24) pagando un recargo adicional en el "
            "mostrador.\n\n"
            "Todos los documentos se deben presentar en formato físico al momento "
            "de retirar el vehículo. Además, algunos requisitos pueden cambiar de "
            "acuerdo a tu país de origen, puedes consultar cuáles son a través de "
            "nuestro Chatbot."
        )

        return {
            "faq_1": faq_1,
            "faq_2": faq_2,
            "faq_3": faq_3,
            "faq_4": faq_4,
        }

    def generate_vjm_carrental(self, ciudad: str, estado: str = "",
                               tit: str = "", estado_abrev: str = "",
                               car_types: Optional[list] = None) -> dict:
        """VJM B5: carRental — H2 45-52p (LLM) + H3 templates (19-29p).

        5 tipos de auto según loadContentVjs.xlsx:
        Lujo, SUVs, Vans, Convertibles, Eléctricos.
        """
        abrev = estado_abrev or (estado[:2].upper() if estado else "")
        ub_corto = f"{ciudad}, {abrev}" if abrev else ciudad
        ubicacion = f"{ciudad}, {estado}" if estado else ciudad

        if not tit:
            tit = (f"Alquiler de autos económicos y otros vehículos para "
                   f"movilizarte por {ub_corto}")
        if not car_types:
            car_types = [
                ("Alquiler de Autos de Lujo", "Lujo"),
                ("Renta de SUVs", "SUVs"),
                ("Alquiler de Vans", "Vans"),
                ("Renta de Convertibles", "Convertibles"),
                ("Alquiler de Eléctricos", "Eléctricos"),
            ]

        # ── H3 templates fijos por tipo de auto (estilo loadContentVjs) ──
        _templates_h3 = {
            "Lujo": (
                f"Alquila un auto de lujo en {ciudad}. ¡Combina elegancia "
                f"y comodidad! Es la mejor opción para viajeros que buscan "
                f"una experiencia premium a precios accesibles."
            ),
            "SUVs": (
                f"Descubre la potencia y versatilidad de nuestras SUVs de "
                f"alquiler en {ciudad}. Son perfectas para familias, grupos "
                f"o aventureros que necesitan espacio y tracción."
            ),
            "Vans": (
                f"Viaja en grupo por {ciudad} gracias a una van de alquiler. "
                f"Ideal para excursiones familiares o cualquier tipo de viaje "
                f"largo con la máxima comodidad."
            ),
            "Convertibles": (
                f"Siente la brisa de {ciudad} con nuestros convertibles de "
                f"renta. Disfruta de las vistas panorámicas mientras conduces "
                f"con el techo abierto al mejor precio."
            ),
            "Eléctricos": (
                f"Únete al futuro sostenible con nuestro alquiler de "
                f"vehículos eléctricos en {ciudad}: eficiencia energética "
                f"y confort en cada trayecto."
            ),
        }

        # ── H2 desc se genera con LLM (45-52 palabras) ──
        prompt = (
            "Ejemplo de referencia:\n"
            "'Con Viajemos, tu aventura inicia con precios bajos en una "
            "amplia selección de carros para alquilar en Orlando. Compara "
            "opciones de lujo, SUVs, vans, convertibles y eléctricos. "
            "Reserva fácilmente el vehículo ideal para recorrer la ciudad, "
            "ir a la playa o hacer road trips inolvidables.'\n\n"
            f"Nuevo tema: {ubicacion}\n"
            "Reglas para desc: EXACTAMENTE 45 a 52 palabras.\n"
            "Menciona variedad de tipos de vehículo. Invita a comparar.\n\n"
            "Genera SOLO el H2:\n"
            f"|tit: {tit}|\n"
            "|desc: descripción H2|"
        )
        raw = self._call(SYSTEM_VJM, prompt, max_tokens=2000)
        fields = self.parse_fields(raw)
        if "tit" not in fields:
            fields["tit"] = tit

        # Agregar H3 templates
        for i, ct in enumerate(car_types):
            if isinstance(ct, tuple):
                h3_tit, tipo_key = ct
            else:
                h3_tit = ct
                tipo_key = ct
            fields[f"tit_{i+1}"] = h3_tit
            fields[f"desc_{i+1}"] = _templates_h3.get(
                tipo_key,
                f"Renta un {tipo_key.lower()} en {ub_corto} con las mejores tarifas."
            )

        return fields

    # Lista FIJA de 6 ciudades para favoriteCities VJM (siempre las mismas).
    # Evita dependencia del LLM que suele fallar llenando H3 aqui.
    # ── 17 ciudades estándar (Miami→Austin) con KWs y frases comerciales ──
    # Cada ciudad tiene: (nombre, estado, H3_title, desc_text)
    # Los H3 rotan KWs: alquiler/renta de autos/carros/vehiculos
    # Los desc tienen frase comercial estilo produccion real
    CIUDADES_ESTANDAR_17 = [
        ("Miami", "Florida",
         "Alquiler de autos en Miami",
         "¡Miami te espera! Compara tarifas de alquiler de autos y recorre "
         "South Beach, Wynwood y el downtown con total libertad. ¡Reserva ya!"),
        ("Orlando", "Florida",
         "Renta de autos en Orlando",
         "¡Orlando es pura diversión! Renta un auto y recorre los mejores "
         "parques temáticos a tu ritmo. Tarifas desde USD $8 al día."),
        ("CBX", "",
         "Alquiler de carros en CBX",
         "¡Cruza la frontera sin estrés! Alquila un auto en CBX y empieza "
         "tu aventura al mejor precio. Reserva rápida y segura."),
        ("Las Vegas", "Nevada",
         "Renta de autos en Las Vegas",
         "¡Las Vegas te llama! Renta un auto y recorre el Strip, los shows "
         "y el desierto con libertad total. Tarifas que te van a encantar."),
        ("Nueva York", "New York",
         "Alquiler de autos en Nueva York",
         "¡La Gran Manzana a tu alcance! Alquila un auto y recorre Manhattan, "
         "Brooklyn y más sin depender del metro. ¡Compara y ahorra!"),
        ("Los Ángeles", "California",
         "Renta de autos en Los Ángeles",
         "¡Hollywood, Santa Mónica y la Costa del Pacífico! Renta un auto en "
         "Los Ángeles y vive California con estilo. ¡Reserva ahora!"),
        ("Houston", "Texas",
         "Alquiler de autos en Houston",
         "¡Houston, tenemos ofertas! Alquila un auto y recorre la capital del "
         "espacio a tu ritmo. Precios bajos y kilómetros ilimitados."),
        ("Chicago", "Illinois",
         "Renta de carros en Chicago",
         "¡La Ciudad del Viento te espera! Renta un auto en Chicago y vive "
         "la arquitectura, el jazz y la pizza deep-dish. ¡Compara tarifas!"),
        ("Fort Lauderdale", "Florida",
         "Alquiler de carros en Fort Lauderdale",
         "¡Sol, playas y libertad! Alquila un auto en Fort Lauderdale y recorre "
         "la costa de Florida con las mejores tarifas. ¡Anímate!"),
        ("San Diego", "California",
         "Renta de autos en San Diego",
         "¡San Diego te enamora! Renta un auto y recorre Gaslamp Quarter, "
         "La Jolla y el Zoo con total libertad. ¡Compara y reserva!"),
        ("Dallas", "Texas",
         "Alquiler de autos en Dallas",
         "¡Texas en grande! Alquila un auto en Dallas y recorre la ciudad "
         "con estilo. Tarifas competitivas y reserva en minutos."),
        ("Phoenix", "Arizona",
         "Renta de carros en Phoenix",
         "¡El desierto te espera! Renta un auto en Phoenix y explora el "
         "Gran Cañón, Sedona y más. Precios bajos y sin complicaciones."),
        ("Tampa", "Florida",
         "Alquiler de autos en Tampa",
         "¡Tampa Bay es increíble! Alquila un auto y recorre las playas de "
         "Clearwater, Ybor City y Busch Gardens. ¡Reserva ya!"),
        ("San Francisco", "California",
         "Renta de autos en San Francisco",
         "¡El Golden Gate te espera! Renta un auto en San Francisco y recorre "
         "Fisherman's Wharf, Napa Valley y la costa. ¡Compara ahora!"),
        ("Atlanta", "Georgia",
         "Alquiler de autos en Atlanta",
         "¡Atlanta vibra con energía! Alquila un auto y recorre el centro, "
         "el acuario y Piedmont Park. Tarifas que se ajustan a tu plan."),
        ("Denver", "Colorado",
         "Renta de carros en Denver",
         "¡Las Montañas Rocosas te llaman! Renta un auto en Denver y vive "
         "aventuras de altura. Precios bajos y kilómetros ilimitados."),
        ("Austin", "Texas",
         "Alquiler de autos en Austin",
         "¡Austin es pura vibra! Alquila un auto y recorre la capital de la "
         "música en vivo. Reserva rápida, segura y sin complicaciones."),
    ]

    def generate_vjm_favoritecities(self, ciudad: str, estado: str = "",
                                    tit: str = "",
                                    locations: Optional[list] = None) -> dict:
        """VJM B6: favoriteCities — H2 LLM 55-66p + 17 ciudades estándar con desc.

        Las 17 ciudades son siempre las mismas (Miami→Austin).
        Cada desc tiene KW + frase comercial estilo producción real.
        Si se pasan locations explícitas (localidades de BD), se usan esas.
        """
        ubicacion = f"{ciudad}, {estado}" if estado else ciudad

        if not tit:
            tit = (f"Renta de autos en las principales ciudades de Estados Unidos")

        # ── H2 desc con LLM (55-66 palabras) ──
        prompt_h2 = (
            "Ejemplo de referencia:\n"
            "'Explora las principales ciudades de Estados Unidos con un auto de "
            "alquiler. Con Viajemos, accede a las mejores tarifas en renta de autos "
            "y recorre cada destino con total libertad. Compara precios de agencias "
            "reconocidas y elige la opción ideal para tu viaje.'\n\n"
            f"Nuevo tema: {ubicacion}\n"
            "Reglas para desc: EXACTAMENTE 55 a 66 palabras.\n"
            "Contexto: Viajemos ofrece renta de autos en las principales ciudades "
            "de Estados Unidos. Invita a comparar precios y elegir la mejor opción.\n"
            "IMPORTANTE: No empieces con 'Descubre'.\n\n"
            "Genera SOLO el H2:\n"
            f"|tit: {tit}|\n"
            "|desc: descripción H2|"
        )
        raw = self._call(SYSTEM_VJM, prompt_h2, max_tokens=2000)
        fields = self.parse_fields(raw)
        if "tit" not in fields:
            fields["tit"] = tit

        # ── H3: 17 ciudades estándar con desc comercial ──
        cities = self.CIUDADES_ESTANDAR_17
        if locations:
            # Si se pasan localidades explícitas, usar esas en vez de las 17
            for i, loc in enumerate(locations):
                if isinstance(loc, tuple):
                    loc_name = loc[0]
                else:
                    loc_name = loc
                fields[f"tit_{i+1}"] = f"Alquiler de autos en {loc_name}"
                fields[f"desc_{i+1}"] = (
                    f"Renta de autos en {loc_name}: aprovecha las mejores tarifas "
                    f"de alquiler de vehiculos con {self.brand_name}. Compara "
                    f"precios y reserva online."
                )
        else:
            for i, (name, state, h3_title, desc_text) in enumerate(cities):
                fields[f"tit_{i+1}"] = h3_title
                fields[f"desc_{i+1}"] = desc_text

        return fields

    # ══════════════════════════════════════════════════════════════════
    # TRADUCCIÓN
    # ══════════════════════════════════════════════════════════════════

    def translate(self, text: str, target_lang: str) -> str:
        if target_lang.lower() in ("en", "english", "inglés"):
            system = SYSTEM_TRANSLATE_EN
            instruction = "Translate this Spanish text to English:"
        elif target_lang.lower() in ("pt", "portuguese", "portugués"):
            system = SYSTEM_TRANSLATE_PT
            instruction = "Traduza este texto em espanhol para português:"
        else:
            raise ValueError(f"Idioma no soportado: {target_lang}")

        raw = self._call(system, f"{instruction}\n\n{text}",
                         temperature=LM_TRANSLATE_TEMP, max_tokens=4000)
        return raw.strip()

    def translate_fields(self, fields: dict, target_lang: str) -> dict:
        parts = []
        for k, v in fields.items():
            if v and v.strip():
                parts.append(f"|{k}: {v}|")
        if not parts:
            return {}
        text = "\n".join(parts)
        translated = self.translate(text, target_lang)
        return self.parse_fields(translated)


# ── Demo ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    client = LMClient()
    models = client.ping()
    log.info("Modelos disponibles: %s", models)

    log.info("Generando quicksearch para Memphis...")
    qs = client.generate_quicksearch("Memphis", "Tennessee")
    log.info("Quicksearch: %s", qs)
