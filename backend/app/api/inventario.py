"""
Módulo de inventario de tarjetas — /api/v1/inventario/

Permite a la administración:
  - Configurar los tipos de tarjeta que vende (nombre, tipo de acceso, precio)
  - Llevar el stock en bodega (entradas por compra de lotes, ajustes)
  - Consultar el inventario y el historial de movimientos

La VENTA de tarjetas (que baja el stock y genera ingreso) ocurre en el módulo
de caja, no aquí. Aquí se gestiona el catálogo y el stock.
"""
import datetime as dt

from flask import Blueprint, request, jsonify

from app.extensions import db
from app.models.cuenta import TipoTarjeta, MovimientoStock
from app.auth.security import roles_required, requiere_funcion_plan

inventario_bp = Blueprint("inventario", __name__)


def _err(code, msg, status):
    return jsonify({"error": {"code": code, "message": msg}}), status


# ── Listar tipos de tarjeta (catálogo + stock) ────────────────────────────────
@inventario_bp.get("/tipos")
@roles_required("admin", "super_admin", "cajero", "desarrollador")
@requiere_funcion_plan("cuotas")
def listar_tipos(usuario_actual):
    from app.utils.residencial import scope_directo
    tipos = scope_directo(TipoTarjeta.query, TipoTarjeta, usuario_actual).order_by(
        TipoTarjeta.nombre.asc()).all()
    return jsonify({"data": [t.to_dict() for t in tipos]})


# ── Crear un tipo de tarjeta ──────────────────────────────────────────────────
@inventario_bp.post("/tipos")
@roles_required("admin", "super_admin")
@requiere_funcion_plan("cuotas")
def crear_tipo(usuario_actual):
    data = request.get_json(silent=True) or {}
    nombre = (data.get("nombre") or "").strip()
    tipo_acceso = (data.get("tipo_acceso") or "vehicular").strip()
    if not nombre:
        return _err("nombre_requerido", "El nombre es obligatorio", 400)
    if tipo_acceso not in ("vehicular", "peatonal"):
        tipo_acceso = "vehicular"
    try:
        precio = round(float(data.get("precio") or 0), 2)
    except (TypeError, ValueError):
        return _err("precio_invalido", "Precio inválido", 400)
    if precio < 0:
        return _err("precio_invalido", "El precio no puede ser negativo", 400)

    try:
        stock_inicial = int(data.get("stock") or 0)
    except (TypeError, ValueError):
        stock_inicial = 0
    if stock_inicial < 0:
        stock_inicial = 0

    from app.utils.residencial import residencial_id_heredado
    tipo = TipoTarjeta(nombre=nombre, tipo_acceso=tipo_acceso,
                       precio=precio, stock=stock_inicial,
                       residencial_id=residencial_id_heredado(usuario_actual))
    db.session.add(tipo)
    db.session.flush()  # para tener el id

    if stock_inicial > 0:
        db.session.add(MovimientoStock(
            tipo_tarjeta_id=tipo.id, tipo_movimiento="entrada",
            cantidad=stock_inicial, stock_resultante=stock_inicial,
            nota="Stock inicial al crear el tipo", registrado_por=usuario_actual.id,
        ))
    db.session.commit()
    return jsonify({"data": tipo.to_dict()}), 201


# ── Editar un tipo (nombre, precio, activo) ───────────────────────────────────
@inventario_bp.put("/tipos/<uuid>")
@roles_required("admin", "super_admin")
@requiere_funcion_plan("cuotas")
def editar_tipo(usuario_actual, uuid):
    from app.utils.residencial import pertenece_a_mi_residencial
    tipo = TipoTarjeta.query.filter_by(uuid_publico=uuid).first()
    # Día 48 — hallazgo de auditoría: sin este chequeo, un admin de otra
    # residencial podía editar precio/nombre/stock de un tipo de tarjeta
    # ajeno con solo conocer el UUID.
    if not tipo or not pertenece_a_mi_residencial(tipo, usuario_actual):
        return _err("no_encontrado", "Tipo de tarjeta no encontrado", 404)
    data = request.get_json(silent=True) or {}
    if "nombre" in data and data["nombre"].strip():
        tipo.nombre = data["nombre"].strip()
    if "precio" in data:
        try:
            p = round(float(data["precio"]), 2)
            if p >= 0:
                tipo.precio = p
        except (TypeError, ValueError):
            pass
    if "tipo_acceso" in data and data["tipo_acceso"] in ("vehicular", "peatonal"):
        tipo.tipo_acceso = data["tipo_acceso"]
    if "activo" in data:
        tipo.activo = bool(data["activo"])
    db.session.commit()
    return jsonify({"data": tipo.to_dict()})


# ── Registrar entrada de stock (compra de un lote nuevo) ──────────────────────
@inventario_bp.post("/tipos/<uuid>/stock")
@roles_required("admin", "super_admin")
@requiere_funcion_plan("cuotas")
def agregar_stock(usuario_actual, uuid):
    # O3.1 / O6.1 (Auditoría Día 42): candado sobre el TipoTarjeta. Sin él,
    # dos ajustes simultáneos leen el mismo tipo.stock y el segundo pisa al
    # primero (last-write-wins), perdiéndose una entrada de bodega. Es el
    # mismo tipo de fila que se bloquea en vender_tarjeta (caja.py), así que
    # ambos flujos quedan coherentes.
    tipo = (TipoTarjeta.query
            .filter_by(uuid_publico=uuid)
            .with_for_update()
            .first())
    if not tipo:
        return _err("no_encontrado", "Tipo de tarjeta no encontrado", 404)
    from app.utils.residencial import pertenece_a_mi_residencial
    if not pertenece_a_mi_residencial(tipo, usuario_actual):
        db.session.rollback()  # soltar el candado antes de salir
        return _err("no_encontrado", "Tipo de tarjeta no encontrado", 404)
    data = request.get_json(silent=True) or {}
    try:
        cantidad = int(data.get("cantidad"))
    except (TypeError, ValueError):
        return _err("cantidad_invalida", "Cantidad inválida", 400)
    if cantidad == 0:
        return _err("cantidad_invalida", "La cantidad no puede ser cero", 400)

    # Permite tanto entrada (compra) como ajuste negativo (corrección de bodega)
    nuevo_stock = tipo.stock + cantidad
    if nuevo_stock < 0:
        return _err("stock_negativo",
                    f"El ajuste dejaría el stock en negativo (actual: {tipo.stock})", 400)
    tipo.stock = nuevo_stock

    db.session.add(MovimientoStock(
        tipo_tarjeta_id=tipo.id,
        tipo_movimiento="entrada" if cantidad > 0 else "ajuste",
        cantidad=cantidad, stock_resultante=nuevo_stock,
        nota=(data.get("nota") or "").strip()[:255] or None,
        registrado_por=usuario_actual.id,
    ))
    db.session.commit()
    return jsonify({"data": tipo.to_dict()})


# ── Historial de movimientos de stock ─────────────────────────────────────────
@inventario_bp.get("/movimientos")
@roles_required("admin", "super_admin", "desarrollador")
@requiere_funcion_plan("cuotas")
def listar_movimientos(usuario_actual):
    movs = (MovimientoStock.query
            .order_by(MovimientoStock.created_at.desc())
            .limit(100).all())
    return jsonify({"data": [m.to_dict() for m in movs]})
