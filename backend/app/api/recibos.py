"""
Módulo de Recibos — /api/v1/recibos/

FASE 1: recibo de pago básico con correlativo interno.
Estructura preparada para FASE 2 (SAR): CAI, rango autorizado, fecha límite.

- asignar_recibo(pago): reserva el correlativo y lo guarda en el pago.
  Se llama cuando un pago pasa a 'aprobado'.
- GET /recibos/<pago_uuid>/pdf: genera el PDF del recibo.
- GET/PUT /recibos/config: ver y editar la configuración del emisor.
"""
import io

from flask import Blueprint, jsonify, request, send_file

from app.extensions import db
from app.models.cuenta import Pago, ConfigRecibo
from app.auth.security import roles_required, token_required

recibos_bp = Blueprint("recibos", __name__)


def asignar_recibo(pago):
    """
    Asigna un número de recibo correlativo a un pago aprobado, si aún no tiene.
    Idempotente: si el pago ya tiene número, no hace nada.
    NOTA: el caller es responsable del commit.
    """
    if pago.numero_recibo:
        return pago.numero_recibo
    cfg = ConfigRecibo.get()
    pago.numero_recibo = cfg.siguiente_correlativo()
    return pago.numero_recibo


def _err(code, msg, status):
    return jsonify({"error": {"code": code, "message": msg}}), status


# ─────────────────────────────────────────────────────────────────────────────
# Configuración del recibo (emisor + datos SAR)
# ─────────────────────────────────────────────────────────────────────────────
@recibos_bp.get("/config")
@roles_required("admin", "super_admin")
def ver_config(usuario_actual):
    return jsonify({"data": ConfigRecibo.get().to_dict()})


@recibos_bp.put("/config")
@roles_required("admin", "super_admin")
def editar_config(usuario_actual):
    cfg = ConfigRecibo.get()
    data = request.get_json(silent=True) or {}
    # Datos del emisor (Fase 1)
    for campo in ["nombre_emisor", "rtn_emisor", "direccion_emisor", "telefono_emisor", "prefijo"]:
        if campo in data:
            setattr(cfg, campo, (data[campo] or "").strip() or None)
    db.session.commit()
    return jsonify({"data": cfg.to_dict()})


# ─────────────────────────────────────────────────────────────────────────────
# Generar PDF del recibo de un pago
# ─────────────────────────────────────────────────────────────────────────────
@recibos_bp.get("/<pago_uuid>/pdf")
@token_required
def recibo_pdf(usuario_actual, pago_uuid):
    pago = Pago.query.filter_by(uuid_publico=pago_uuid).first()
    if not pago:
        return _err("no_encontrado", "Pago no encontrado", 404)
    if pago.estado != "aprobado":
        return _err("no_aprobado", "Solo se generan recibos de pagos aprobados", 400)

    # Autorización: roles administrativos/operativos ven cualquier recibo.
    # Un residente solo puede ver el recibo de un pago de SU cuenta.
    roles_admin = ("admin", "super_admin", "cajero", "guardia", "desarrollador")
    if usuario_actual.rol not in roles_admin:
        cuenta = pago.cuenta
        es_suyo = cuenta and any(
            r.usuario_id == usuario_actual.id and r.activo for r in cuenta.residentes)
        if not es_suyo:
            return _err("sin_permiso", "No tenés permiso para ver este recibo", 403)

    # Asignar correlativo si por alguna razón no lo tiene
    if not pago.numero_recibo:
        asignar_recibo(pago)
        db.session.commit()

    cfg = ConfigRecibo.get()
    pdf_bytes = _generar_pdf_recibo(pago, cfg)
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=False,
        download_name=f"recibo-{cfg.numero_formateado(pago.numero_recibo)}.pdf",
    )


def _generar_pdf_recibo(pago, cfg):
    """Genera el PDF del recibo con reportlab."""
    from reportlab.lib.pagesizes import A5
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas

    AZUL = colors.HexColor("#022E45")
    NARANJA = colors.HexColor("#F48723")
    GRIS = colors.HexColor("#6b7280")

    buf = io.BytesIO()
    W, H = A5
    c = canvas.Canvas(buf, pagesize=A5)

    numero = cfg.numero_formateado(pago.numero_recibo)

    # Encabezado
    c.setFillColor(NARANJA)
    c.rect(0, H - 18 * mm, W, 18 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(12 * mm, H - 12 * mm, cfg.nombre_emisor or "Residencial Villas del Sol")

    # Título RECIBO + número
    c.setFillColor(AZUL)
    c.setFont("Helvetica-Bold", 15)
    c.drawRightString(W - 12 * mm, H - 30 * mm, "RECIBO DE PAGO")
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(NARANJA)
    c.drawRightString(W - 12 * mm, H - 36 * mm, f"No. {numero}")

    # Datos del emisor
    y = H - 30 * mm
    c.setFillColor(GRIS)
    c.setFont("Helvetica", 8)
    if cfg.rtn_emisor:
        c.drawString(12 * mm, y, f"RTN: {cfg.rtn_emisor}")
        y -= 4 * mm
    if cfg.direccion_emisor:
        c.drawString(12 * mm, y, cfg.direccion_emisor)
        y -= 4 * mm
    if cfg.telefono_emisor:
        c.drawString(12 * mm, y, f"Tel: {cfg.telefono_emisor}")
        y -= 4 * mm

    # Línea separadora
    y -= 3 * mm
    c.setStrokeColor(colors.HexColor("#e3e9f2"))
    c.setLineWidth(0.8)
    c.line(12 * mm, y, W - 12 * mm, y)
    y -= 8 * mm

    # Datos del pago
    cuenta = pago.cuenta
    unidad = cuenta.unidad.identificador if cuenta and cuenta.unidad else "—"
    if cuenta and cuenta.apartamento:
        unidad = f"{unidad} · Apto {cuenta.apartamento}"
    titular = "—"
    if cuenta:
        tit = next((r for r in cuenta.residentes if r.rol_cuenta == "titular"), None)
        if tit and tit.usuario:
            titular = f"{tit.usuario.nombre} {tit.usuario.apellido}"

    fecha = pago.revisado_en or pago.created_at
    fecha_str = fecha.strftime("%d/%m/%Y %I:%M %p") if fecha else "—"

    metodo_label = {
        "efectivo": "Efectivo", "tarjeta_pos": "Tarjeta POS",
        "transferencia": "Transferencia", "linea": "Pago en línea", "pasarela": "Pago en línea",
    }.get(pago.metodo, pago.metodo)

    def fila(label, valor, bold_val=False):
        nonlocal y
        c.setFont("Helvetica", 9)
        c.setFillColor(GRIS)
        c.drawString(12 * mm, y, label)
        c.setFont("Helvetica-Bold" if bold_val else "Helvetica", 9)
        c.setFillColor(AZUL)
        c.drawRightString(W - 12 * mm, y, str(valor))
        y -= 6.5 * mm

    fila("Fecha:", fecha_str)
    fila("Casa / Unidad:", unidad)
    fila("Recibí de:", titular)
    fila("Concepto:", (pago.referencia or "Pago de cuota")[:40])
    fila("Forma de pago:", metodo_label)

    # Monto destacado
    y -= 4 * mm
    c.setFillColor(colors.HexColor("#f9fbfd"))
    c.rect(12 * mm, y - 8 * mm, W - 24 * mm, 14 * mm, fill=1, stroke=0)
    c.setStrokeColor(NARANJA)
    c.setLineWidth(1)
    c.rect(12 * mm, y - 8 * mm, W - 24 * mm, 14 * mm, fill=0, stroke=1)
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(GRIS)
    c.drawString(16 * mm, y - 1 * mm, "TOTAL PAGADO")
    c.setFont("Helvetica-Bold", 16)
    c.setFillColor(NARANJA)
    monto_str = "L " + f"{float(pago.monto):,.2f}"
    c.drawRightString(W - 16 * mm, y - 2.5 * mm, monto_str)
    y -= 18 * mm

    # Pie / aviso de fase
    c.setFont("Helvetica-Oblique", 6.5)
    c.setFillColor(GRIS)
    if cfg.fase_sar_activa and cfg.cai:
        # Fase 2 — datos fiscales
        c.drawString(12 * mm, 18 * mm, f"CAI: {cfg.cai}")
        if cfg.fecha_limite_emision:
            c.drawString(12 * mm, 14 * mm, f"Fecha límite de emisión: {cfg.fecha_limite_emision.strftime('%d/%m/%Y')}")
        if cfg.rango_desde and cfg.rango_hasta:
            c.drawString(12 * mm, 10 * mm,
                         f"Rango autorizado: {cfg.rango_desde:08d} al {cfg.rango_hasta:08d}")
    else:
        c.drawString(12 * mm, 14 * mm,
                     "Comprobante interno de pago. No es un documento fiscal válido para crédito fiscal.")
        c.drawString(12 * mm, 10 * mm,
                     "La facturación con estructura SAR (CAI) se habilitará en una fase posterior.")

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()
