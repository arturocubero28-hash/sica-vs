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

from flask import Blueprint, jsonify, request, send_file, current_app

from app.extensions import db
from app.models.cuenta import Pago, ConfigRecibo
from app.auth.security import roles_required, token_required, requiere_funcion_plan

recibos_bp = Blueprint("recibos", __name__)


def asignar_recibo(pago):
    """
    Asigna un número de recibo correlativo a un pago aprobado, si aún no tiene.
    Idempotente: si el pago ya tiene número, no hace nada.
    NOTA: el caller es responsable del commit.

    Día 48: la residencial se resuelve DESDE EL PROPIO PAGO (vía
    cuenta→unidad), no desde quien llama — así los tres call sites
    (caja.py, cuotas.py, arreglos.py) no necesitan cambios, y el
    correlativo que se asigna siempre es el de la residencial correcta.
    """
    if pago.numero_recibo:
        return pago.numero_recibo
    unidad = pago.cuenta.unidad if pago.cuenta else None
    rid = unidad.residencial_id if unidad else None
    cfg = ConfigRecibo.get(rid)
    pago.numero_recibo = cfg.siguiente_correlativo()
    return pago.numero_recibo


def _err(code, msg, status):
    return jsonify({"error": {"code": code, "message": msg}}), status


# ─────────────────────────────────────────────────────────────────────────────
# Configuración del recibo (emisor + datos SAR)
# ─────────────────────────────────────────────────────────────────────────────
@recibos_bp.get("/config")
@roles_required("admin", "super_admin")
@requiere_funcion_plan("cuotas")
def ver_config(usuario_actual):
    # Día 48: mismo resolver que ya usa Caja (genérico pese al nombre —
    # admin/supervisor -> su propia residencial; super_admin/desarrollador
    # -> deben indicarla explícita con ?residencial_id).
    from app.utils.residencial import resolver_residencial_caja
    rid, err = resolver_residencial_caja(usuario_actual, request)
    if err:
        return err
    return jsonify({"data": ConfigRecibo.get(rid).to_dict()})


@recibos_bp.put("/config")
@roles_required("admin", "super_admin")
@requiere_funcion_plan("cuotas")
def editar_config(usuario_actual):
    from app.utils.residencial import resolver_residencial_caja
    rid, err = resolver_residencial_caja(usuario_actual, request)
    if err:
        return err
    cfg = ConfigRecibo.get(rid)
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
@requiere_funcion_plan("cuotas")
def recibo_pdf(usuario_actual, pago_uuid):
    pago = Pago.query.filter_by(uuid_publico=pago_uuid).first()
    if not pago:
        return _err("no_encontrado", "Pago no encontrado", 404)

    # Día 48 — hallazgo de auditoría: antes había DOS chequeos de
    # autorización en esta función (uno más abajo, preexistente) que
    # trataban admin/cajero/guardia/desarrollador como "ven cualquier
    # recibo" SIN verificar residencial — cualquiera de esos roles podía
    # generar/ver el PDF de un pago ajeno (nombre, monto, unidad de un
    # residente de otra residencial) con solo conocer el UUID. Se
    # consolida en un solo chequeo correcto, manteniendo que
    # admin/cajero/guardia SÍ ven cualquier recibo — pero solo de SU
    # propia residencial.
    unidad = pago.cuenta.unidad if pago.cuenta else None
    rid_pago = unidad.residencial_id if unidad else None

    es_plataforma = usuario_actual.rol in ("super_admin", "desarrollador")
    es_staff_de_su_residencial = (
        usuario_actual.rol in ("admin", "cajero", "guardia")
        and (rid_pago is None or usuario_actual.residencial_id is None
             or rid_pago == usuario_actual.residencial_id)
    )
    es_dueno = False
    if not (es_plataforma or es_staff_de_su_residencial):
        cuenta = pago.cuenta
        es_dueno = bool(cuenta and any(
            r.usuario_id == usuario_actual.id and r.activo for r in cuenta.residentes))
    if not (es_plataforma or es_staff_de_su_residencial or es_dueno):
        return _err("sin_permiso", "No tenés permiso para ver este recibo", 403)

    if pago.estado != "aprobado":
        return _err("no_aprobado", "Solo se generan recibos de pagos aprobados", 400)

    # Asignar correlativo si por alguna razón no lo tiene
    if not pago.numero_recibo:
        asignar_recibo(pago)
        db.session.commit()

    cfg = ConfigRecibo.get(rid_pago)
    pdf_bytes = _generar_pdf_recibo(pago, cfg)
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=False,
        download_name=f"recibo-{cfg.numero_formateado(pago.numero_recibo)}.pdf",
    )


def _generar_pdf_recibo(pago, cfg):
    """
    Genera el PDF del recibo con reportlab.

    Día 54 — corrección real encontrada por el usuario probando con una
    segunda residencial (Bosques de Jucutuma): el recibo mostraba
    "Residencial Villas del Sol" fijo (el nombre real solo salía si el
    admin había configurado nombre_emisor a mano en ConfigRecibo — Bosques
    nunca lo hizo), colores fijos sin importar la personalización de cada
    residencial, sin logo, y el concepto no decía a qué mes correspondía
    la cuota. Ahora usa el nombre/colores/logo REALES de la residencial
    del pago (Residencial.nombre, color_primario/secundario, logo_archivo)
    como el criterio por defecto -- nombre_emisor en ConfigRecibo sigue
    pudiendo pisarlo si el admin quiere un nombre distinto en el recibo
    (ej. la razón social legal) del que usa en el resto del sistema.
    """
    import os
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas

    from app.models.residencial import Residencial, DEFAULT_COLOR_PRIMARIO, DEFAULT_COLOR_SECUNDARIO
    residencial = Residencial.query.get(pago.residencial_id) if pago.residencial_id else None

    AZUL = colors.HexColor((residencial.color_primario if residencial else None) or DEFAULT_COLOR_PRIMARIO)
    NARANJA = colors.HexColor((residencial.color_secundario if residencial else None) or DEFAULT_COLOR_SECUNDARIO)
    GRIS = colors.HexColor("#6b7280")

    nombre_emisor = cfg.nombre_emisor or (residencial.nombre if residencial else None) or "Residencial"

    buf = io.BytesIO()
    # Día 54 — pedido del usuario: A5 completo (210mm de alto) dejaba mucho
    # espacio en blanco al final, el contenido real ocupa mucho menos.
    # Tamaño recortado a medida (mismo ancho de A5, alto ajustado al
    # contenido real: header + datos + total + pie, con margen prudente).
    W, H = 148 * mm, 145 * mm
    c = canvas.Canvas(buf, pagesize=(W, H))

    numero = cfg.numero_formateado(pago.numero_recibo)

    # Encabezado — pedido del usuario: la franja debe llegar hasta el borde
    # superior real de la página (antes quedaba un margen blanco arriba), y
    # con las esquinas redondeadas solo abajo (las de arriba se "cortan"
    # solas contra el borde de la página, a propósito: el rectángulo se
    # dibuja más alto de lo que se ve, así el redondeo de arriba queda
    # fuera del área visible y ahí se ve recto, pegado al borde).
    ALTO_HEADER = 22 * mm
    c.setFillColor(NARANJA)
    c.roundRect(0, H - ALTO_HEADER - 6 * mm, W, ALTO_HEADER + 6 * mm, 4 * mm, fill=1, stroke=0)

    # Logo (si la residencial tiene uno), en una placa circular blanca --
    # pedido del usuario: que se vea "profesional, como un círculo", no la
    # imagen cruda pegada sobre el color. Se recorta la imagen en círculo
    # con un clip path (si el logo es rectangular, no se deforma ni se ve
    # el fondo cuadrado asomando).
    x_texto = 12 * mm
    if residencial and residencial.logo_archivo:
        ruta_logo = os.path.join(
            current_app.config.get("UPLOAD_FOLDER", "/app/uploads"), "residenciales", residencial.logo_archivo)
        if os.path.exists(ruta_logo):
            try:
                radio = 7 * mm
                cx, cy = 10 * mm + radio, H - 11 * mm
                # Placa blanca de fondo, un poco más grande que la imagen,
                # para que quede un borde parejo alrededor del logo.
                c.setFillColor(colors.white)
                c.circle(cx, cy, radio + 0.8 * mm, fill=1, stroke=0)
                c.saveState()
                path = c.beginPath()
                path.circle(cx, cy, radio)
                c.clipPath(path, stroke=0, fill=0)
                c.drawImage(ruta_logo, cx - radio, cy - radio, width=radio * 2, height=radio * 2,
                           preserveAspectRatio=True, mask="auto")
                c.restoreState()
                x_texto = cx + radio + 4 * mm
            except Exception:
                pass  # un logo corrupto no debe tumbar la generación del recibo
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(x_texto, H - 13 * mm, nombre_emisor)

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

    # Concepto: si el pago corresponde a una cuota con período conocido, se
    # arma "Pago de cuota — Agosto 2026" en vez del genérico de antes.
    concepto = pago.referencia or "Pago de cuota"
    if not pago.referencia and pago.cuota and pago.cuota.periodo:
        meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
                 "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        p = pago.cuota.periodo
        concepto = f"Pago de cuota — {meses[p.month - 1].capitalize()} {p.year}"

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
    fila("Concepto:", concepto[:40])
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
