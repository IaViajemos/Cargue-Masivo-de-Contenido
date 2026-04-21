"""
rich_text_formatter.py — Aplica colores inline (rich text) a las celdas
de Secciones según las reglas de marca MCR/VJM.

MCR:
  Rojo #e6484b Bold: "Miles Car Rental", descuentos "%"
  Verde #00eba7 Bold: "Seguro de Viaje Gratis", precios "USD $X"
  Morado #9900ff SIN Bold: contenido IP que difiere del H2 base

VJM:
  Azul #0583ff Bold: "Viajemos", precios, descuentos
  Verde #00eba7 Bold: "Seguro de Viaje Gratis"
  Morado #8154ef Bold: contenido IP que difiere del H2 base
"""
import re
from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.cell.text import InlineFont
from openpyxl.drawing.fill import ColorChoice

# ── Colores por marca ──────────────────────────────────────────────

MCR_RED = "FFE6484B"
MCR_GREEN = "FF00EBA7"
MCR_PURPLE = "FF9900FF"

VJM_BLUE = "FF0583FF"
VJM_GREEN = "FF00EBA7"
VJM_PURPLE = "FF8154EF"


def _font(color_argb, bold=True):
    """Crea InlineFont con color y bold."""
    return InlineFont(
        color=color_argb,
        b=bold,
    )


# ── Reglas de colorización ─────────────────────────────────────────

# Patrones que se colorean (regex, color_key)
# Patrones ES (español)
MCR_PATTERNS_ES = [
    (r"Miles Car Rental", "red"),
    (r"descuentos?\s+(?:hasta\s+)?(?:del?\s+)?\d+\s*%", "red"),
    (r"\d+\s*%\s*(?:OFF|de\s+descuento)", "red"),
    (r"35\s*%", "red"),
    (r"Seguro de Viaje Gratis(?:\s+para\s+extranjeros)?", "green"),
    (r"Seguro de Viaje GRATIS(?:\s+v[aá]lido\s+para\s+extranjeros)?", "green"),
    (r"Cobertura de Viaje Gratis", "green"),
    (r"USD\s*\$\s*\d+(?:\s*al\s+d[ií]a)?", "green"),
    (r"desde\s+(?:los\s+)?USD\s*\$\s*\d+", "green"),
]

# Patrones EN (inglés)
MCR_PATTERNS_EN = [
    (r"Miles Car Rental", "red"),
    (r"discounts?\s+(?:up\s+to\s+)?\d+\s*%", "red"),
    (r"\d+\s*%\s*(?:OFF|discount)", "red"),
    (r"35\s*%", "red"),
    (r"Free Travel Insurance(?:\s+for\s+foreigners)?", "green"),
    (r"Free Travel Coverage", "green"),
    (r"USD\s*\$\s*\d+(?:\s*(?:per|a)\s+day)?", "green"),
    (r"from\s+USD\s*\$\s*\d+", "green"),
]

# Patrones PT (portugués)
MCR_PATTERNS_PT = [
    (r"Miles Car Rental", "red"),
    (r"descontos?\s+(?:de\s+até\s+)?\d+\s*%", "red"),
    (r"\d+\s*%\s*(?:OFF|de\s+desconto)", "red"),
    (r"35\s*%", "red"),
    (r"Seguro de Viagem Gr[aá]tis(?:\s+para\s+estrangeiros)?", "green"),
    (r"Cobertura de Viagem Gr[aá]tis", "green"),
    (r"USD\s*\$\s*\d+(?:\s*(?:por|ao)\s+dia)?", "green"),
    (r"a\s+partir\s+de\s+USD\s*\$\s*\d+", "green"),
]

VJM_PATTERNS_ES = [
    (r"Viajemos", "blue"),
    (r"descuentos?\s+(?:hasta\s+)?(?:del?\s+)?\d+\s*%", "blue"),
    (r"\d+\s*%\s*(?:OFF|de\s+descuento)", "blue"),
    (r"35\s*%", "blue"),
    (r"USD\s*\$\s*\d+(?:\s*al\s+d[ií]a)?", "blue"),
    (r"desde\s+(?:los\s+)?USD\s*\$\s*\d+", "blue"),
    (r"Seguro de Viaje Gratis(?:\s+para\s+extranjeros)?", "green"),
    (r"Seguro de Viaje GRATIS(?:\s+v[aá]lido\s+para\s+extranjeros)?", "green"),
    (r"Cobertura de Viaje Gratis", "green"),
]

VJM_PATTERNS_EN = [
    (r"Viajemos", "blue"),
    (r"discounts?\s+(?:up\s+to\s+)?\d+\s*%", "blue"),
    (r"\d+\s*%\s*(?:OFF|discount)", "blue"),
    (r"35\s*%", "blue"),
    (r"USD\s*\$\s*\d+(?:\s*(?:per|a)\s+day)?", "blue"),
    (r"from\s+USD\s*\$\s*\d+", "blue"),
    (r"Free Travel Insurance(?:\s+for\s+foreigners)?", "green"),
    (r"Free Travel Coverage", "green"),
]

VJM_PATTERNS_PT = [
    (r"Viajemos", "blue"),
    (r"descontos?\s+(?:de\s+até\s+)?\d+\s*%", "blue"),
    (r"\d+\s*%\s*(?:OFF|de\s+desconto)", "blue"),
    (r"35\s*%", "blue"),
    (r"USD\s*\$\s*\d+(?:\s*(?:por|ao)\s+dia)?", "blue"),
    (r"a\s+partir\s+de\s+USD\s*\$\s*\d+", "blue"),
    (r"Seguro de Viagem Gr[aá]tis(?:\s+para\s+estrangeiros)?", "green"),
    (r"Cobertura de Viagem Gr[aá]tis", "green"),
]

# Mapeo por marca + idioma
PATTERNS_MAP = {
    ("mcr", "es"): MCR_PATTERNS_ES,
    ("mcr", "en"): MCR_PATTERNS_EN,
    ("mcr", "pt"): MCR_PATTERNS_PT,
    ("vjm", "es"): VJM_PATTERNS_ES,
    ("vjm", "en"): VJM_PATTERNS_EN,
    ("vjm", "pt"): VJM_PATTERNS_PT,
}

# Back-compat
MCR_PATTERNS = MCR_PATTERNS_ES
VJM_PATTERNS = VJM_PATTERNS_ES

MCR_COLORS = {
    "red": _font(MCR_RED, bold=True),
    "green": _font(MCR_GREEN, bold=True),
    "purple": _font(MCR_PURPLE, bold=False),
}

VJM_COLORS = {
    "blue": _font(VJM_BLUE, bold=True),
    "green": _font(VJM_GREEN, bold=True),
    "purple": _font(VJM_PURPLE, bold=True),
}


def colorize_text(text, brand="mcr", lang="es"):
    """Convierte texto plano a CellRichText con colores inline.

    Args:
        text: texto plano (str)
        brand: "mcr" o "vjm"
        lang: "es", "en", "pt"

    Returns:
        CellRichText con TextBlocks coloreados, o str si no hay colores.
    """
    if not text or not isinstance(text, str) or len(text) < 3:
        return text

    patterns = PATTERNS_MAP.get((brand, lang.lower()), MCR_PATTERNS_ES)
    colors = MCR_COLORS if brand == "mcr" else VJM_COLORS

    # Buscar todas las coincidencias con sus posiciones
    matches = []
    for pat, color_key in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            matches.append((m.start(), m.end(), color_key))

    if not matches:
        return text  # Sin colores, devolver string plano

    # Ordenar por posición y eliminar solapamientos
    matches.sort(key=lambda x: x[0])
    filtered = []
    last_end = 0
    for start, end, color_key in matches:
        if start >= last_end:
            filtered.append((start, end, color_key))
            last_end = end

    # Construir CellRichText
    parts = []
    pos = 0
    for start, end, color_key in filtered:
        # Texto plano antes del match
        if start > pos:
            parts.append(text[pos:start])
        # Texto coloreado
        font = colors[color_key]
        parts.append(TextBlock(font, text[start:end]))
        pos = end
    # Texto restante
    if pos < len(text):
        parts.append(text[pos:])

    if len(parts) == 1 and isinstance(parts[0], str):
        return text  # No hubo colorización

    return CellRichText(*parts)


def colorize_fleet_ip(text_base, text_ip, brand="mcr", lang="es"):
    """Coloriza un texto IP (USA/BRA) marcando en MORADO lo que difiere del base.

    Compara text_base (H2) con text_ip (IP) y colorea en morado las frases
    que son diferentes. El resto se colorea con las reglas normales.

    Args:
        text_base: texto H2 original (ES)
        text_ip: texto IP (USA o BRA)
        brand: "mcr" o "vjm"

    Returns:
        CellRichText con morado en las diferencias + colores normales en el resto.
    """
    if not text_base or not text_ip:
        return colorize_text(text_ip, brand, lang)

    colors = MCR_COLORS if brand == "mcr" else VJM_COLORS
    purple_font = colors["purple"]

    # Encontrar la frase que difiere entre base e IP
    # Estrategia: buscar la primera diferencia entre ambos textos
    base_words = text_base.split()
    ip_words = text_ip.split()

    # Encontrar inicio de diferencia
    diff_start = 0
    for i in range(min(len(base_words), len(ip_words))):
        if base_words[i] != ip_words[i]:
            diff_start = i
            break

    # Encontrar fin de diferencia (desde el final)
    diff_end_base = len(base_words)
    diff_end_ip = len(ip_words)
    for i in range(1, min(len(base_words), len(ip_words)) + 1):
        if base_words[-i] != ip_words[-i]:
            diff_end_base = len(base_words) - i + 1
            diff_end_ip = len(ip_words) - i + 1
            break

    if diff_start >= diff_end_ip:
        # No hay diferencia, colorear normalmente
        return colorize_text(text_ip, brand, lang)

    # Calcular posiciones en caracteres
    prefix = " ".join(ip_words[:diff_start])
    diff_text = " ".join(ip_words[diff_start:diff_end_ip])
    suffix = " ".join(ip_words[diff_end_ip:])

    # Construir RichText: prefix normal + diff morado + suffix normal
    parts = []

    if prefix:
        # Colorear prefix con reglas normales
        prefix_rt = colorize_text(prefix + " ", brand)
        if isinstance(prefix_rt, CellRichText):
            parts.extend(prefix_rt)
        else:
            parts.append(prefix + " ")

    # Diferencia en morado
    if diff_text:
        parts.append(TextBlock(purple_font, diff_text))

    if suffix:
        suffix_rt = colorize_text(" " + suffix, brand)
        if isinstance(suffix_rt, CellRichText):
            parts.extend(suffix_rt)
        else:
            parts.append(" " + suffix)

    if not parts:
        return text_ip

    return CellRichText(*parts)
