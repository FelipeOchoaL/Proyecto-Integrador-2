import re
from collections import defaultdict
from io import BytesIO

from fpdf import FPDF


def _limpiar_texto(texto: str, max_chars: int = 500) -> str:
    """Quita tags HTML y recorta el texto."""
    if not texto:
        return ""
    sin_html = re.sub(r"<[^>]+>", " ", texto)
    limpio = re.sub(r"\s+", " ", sin_html).strip()
    if len(limpio) > max_chars:
        return limpio[:max_chars] + "..."
    return limpio


def _safe(texto) -> str:
    """Convierte a str seguro para fpdf (reemplaza caracteres que no soporta latin-1)."""
    if not texto:
        return ""
    return str(texto).encode("latin-1", errors="replace").decode("latin-1")


def generar_pdf_resultados(query: str, resultados: list[dict]) -> bytes:
    """
    Genera un PDF con:
    - Encabezado con la query
    - Resumen por clusters
    - Lista de patentes encontradas
    """
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # --- Encabezado ---
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Patentologos - Reporte de Busqueda", ln=True, align="C")

    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, f"Consulta: \"{_safe(query)}\"", ln=True, align="C")
    pdf.cell(0, 6, f"Total de resultados: {len(resultados)}", ln=True, align="C")
    pdf.ln(8)

    # --- Resumen por clusters ---
    # Agrupar los resultados por cluster_id
    clusters: dict[int | str, list[dict]] = defaultdict(list)
    for pat in resultados:
        cid = pat.get("cluster_id")
        key = cid if cid is not None else "Sin cluster"
        clusters[key].append(pat)

    pdf.set_font("Helvetica", "B", 13)
    pdf.set_fill_color(99, 102, 241)  # indigo
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 9, "  Resumen por Cluster", ln=True, fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    # Tabla simple de clusters
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(238, 242, 255)
    pdf.cell(50, 8, "Cluster", border=1, fill=True)
    pdf.cell(40, 8, "# Patentes", border=1, fill=True)
    pdf.cell(0, 8, "Categoria predominante", border=1, fill=True, ln=True)

    pdf.set_font("Helvetica", "", 10)
    for cid, pats in sorted(clusters.items(), key=lambda x: (str(x[0]) == "Sin cluster", x[0])):
        # Buscar la categoría más frecuente en el cluster
        categorias = [p.get("ww") or p.get("ws") or "" for p in pats]
        categorias = [c for c in categorias if c]
        if categorias:
            cat_predominante = max(set(categorias), key=categorias.count)
        else:
            cat_predominante = "N/A"

        pdf.cell(50, 7, _safe(f"Cluster #{cid}"), border=1)
        pdf.cell(40, 7, str(len(pats)), border=1)
        pdf.cell(0, 7, _safe(cat_predominante[:60]), border=1, ln=True)

    pdf.ln(10)

    # --- Lista de patentes ---
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_fill_color(99, 102, 241)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 9, "  Resultados de la Busqueda", ln=True, fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    for i, pat in enumerate(resultados, start=1):
        # Título de la patente
        titulo = _safe(pat.get("ti") or "Sin titulo")
        pdf.set_font("Helvetica", "B", 10)
        pdf.multi_cell(0, 6, f"{i}. {titulo}")

        # Info básica en una línea
        pn = _safe(pat.get("pn") or "")
        apc = _safe(pat.get("apc") or "")
        pd_val = _safe(pat.get("pd") or "")
        cluster_info = f"Cluster #{pat.get('cluster_id')}" if pat.get("cluster_id") is not None else ""

        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(100, 100, 100)

        info_parts = [x for x in [pn, apc, pd_val, cluster_info] if x]
        pdf.cell(0, 5, " | ".join(info_parts), ln=True)

        # RRF score si viene de búsqueda semántica
        rrf = pat.get("rrf_score")
        if rrf is not None:
            pdf.set_font("Helvetica", "I", 8)
            pdf.cell(0, 4, f"Relevancia RRF: {rrf:.4f}", ln=True)

        # Abstract
        abstract = _limpiar_texto(pat.get("ab") or "")
        if abstract:
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(60, 60, 60)
            pdf.multi_cell(0, 5, _safe(abstract))

        pdf.set_text_color(0, 0, 0)
        pdf.ln(4)

        # Línea separadora entre patentes
        pdf.set_draw_color(200, 200, 200)
        pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x() + 190, pdf.get_y())
        pdf.ln(3)

    # Pie de página
    pdf.ln(5)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 6, "Generado por Patentologos - Sistema de busqueda semantica de patentes", ln=True, align="C")

    buffer = BytesIO()
    pdf.output(buffer)
    return buffer.getvalue()
