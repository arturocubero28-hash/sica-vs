"""
Log de auditoría forense — registra accesos al sistema para diagnóstico.
Cada entrada guarda: usuario, acción (endpoint), método HTTP, IP, timestamp
y el status code de la respuesta.
"""
import datetime as dt
from app.extensions import db


def _now():
    return dt.datetime.now(dt.timezone.utc)


class LogAuditoria(db.Model):
    __tablename__ = "log_auditoria"

    id          = db.Column(db.BigInteger, primary_key=True)
    usuario_id  = db.Column(db.BigInteger, db.ForeignKey("usuarios.id"), nullable=True)
    email       = db.Column(db.String(120))           # por si el usuario no existe aún
    rol         = db.Column(db.String(30))
    metodo      = db.Column(db.String(10))            # GET, POST, etc.
    endpoint    = db.Column(db.String(200))           # /api/v1/auth/login
    status_code = db.Column(db.Integer)               # 200, 401, 500...
    ip          = db.Column(db.String(45))            # IPv4 o IPv6
    user_agent  = db.Column(db.String(300))
    created_at  = db.Column(db.DateTime(timezone=True), default=_now)

    usuario = db.relationship("Usuario", foreign_keys=[usuario_id])

    def descripcion(self):
        """
        Convierte el endpoint técnico en un texto legible para auditoría.

        AUDIT-12 (Auditoría Día 35): cobertura completa de todas las
        operaciones privilegiadas. Cada acción que modifica datos tiene
        su descripción explícita — nada cae al fallback genérico sin
        que sea intencional (consultas GET de bajo impacto).
        """
        e = self.endpoint or ""
        m = self.metodo or ""

        # ── Mapeo exacto (método, endpoint) ────────────────────────
        mapa_exacto = {
            # Autenticación
            ("POST", "/api/v1/auth/login"):               "Inicio de sesión",
            ("GET",  "/api/v1/auth/me"):                  "Verificó su sesión",
            ("POST", "/api/v1/auth/logout"):              "Cerró sesión",
            ("POST", "/api/v1/auth/cambiar-password"):    "Cambió su contraseña",
            ("PUT",  "/api/v1/auth/perfil"):              "Actualizó su perfil",
            ("POST", "/api/v1/auth/activar"):             "Activó su cuenta",
            ("POST", "/api/v1/auth/recuperar"):           "Solicitó recuperación de contraseña",
            ("POST", "/api/v1/auth/reset"):               "Restableció contraseña",
            ("POST", "/api/v1/auth/sesiones/cerrar-otras"): "Cerró todas las otras sesiones",
            # Caja
            ("POST", "/api/v1/caja/abrir"):               "Abrió caja",
            ("POST", "/api/v1/caja/cerrar"):              "Cerró caja",
            ("POST", "/api/v1/caja/pago"):                "Registró pago en ventanilla",
            ("POST", "/api/v1/caja/vender-tarjeta"):      "Vendió tarjeta de acceso",
            ("POST", "/api/v1/caja/saldo-inicial"):       "Modificó saldo inicial de caja",
            ("POST", "/api/v1/caja/ajuste-conteo"):       "Registró ajuste de conteo de caja",
            ("POST", "/api/v1/caja/descuadre"):           "Reportó descuadre de caja",
            ("POST", "/api/v1/caja/salida"):              "Solicitó salida de caja (depósito)",
            ("POST", "/api/v1/caja/ingreso"):             "Solicitó ingreso extraordinario",
            # Cuotas y pagos
            ("POST", "/api/v1/cuotas/generar"):           "Generó cuotas manualmente",
            ("POST", "/api/v1/cuotas/avisar-vencimiento"):"Disparó aviso de vencimiento manual",
            ("POST", "/api/v1/cuotas/revisar-mora"):      "Disparó revisión de mora manual",
            # Cuentas
            ("POST", "/api/v1/cuentas/cuentas"):          "Creó cuenta/casa nueva",
            ("POST", "/api/v1/cuentas/tarifas"):          "Creó tarifa",
            ("PUT",  "/api/v1/cuentas/config-residencial"): "Editó configuración del residencial",
            ("PUT",  "/api/v1/cuentas/mi-residencial"):   "Editó datos de mi residencial",
            ("POST", "/api/v1/cuentas/mi-residencial/logo"): "Subió logo del residencial",
            ("POST", "/api/v1/cuentas/solicitudes-baja"): "Solicitó baja de cuenta (residente)",
            # Usuarios
            ("POST", "/api/v1/usuarios/cajeros"):          "Creó usuario cajero",
            ("POST", "/api/v1/usuarios/supervisores"):     "Creó usuario supervisor",
            ("POST", "/api/v1/usuarios/desarrolladores"):  "Creó usuario desarrollador",
            # Guardia
            ("POST", "/api/v1/guardias/mi-punto-acceso"):  "Guardia fijó su punto de acceso",
            ("POST", "/api/v1/guardias/abrir-manual"):     "Apertura manual de barrera (guardia)",
            # Visitas
            ("POST", "/api/v1/visitas/qr/validar"):       "Validó código QR (guardia)",
            ("POST", "/api/v1/visitas/accesos/visita"):   "Registró acceso de visita con fotos",
            # Acceso físico (admin)
            ("POST", "/api/v1/acceso/puntos"):             "Creó punto de acceso",
            # Acceso físico (dispositivos Pi — sin usuario)
            ("POST", "/api/v1/acceso/validar-tarjeta"):   "Validación de tarjeta (Pi agent)",
            ("POST", "/api/v1/acceso/reportar"):          "Reporte de eventos (Pi agent)",
            ("POST", "/api/v1/acceso/camaras/heartbeat"): "Heartbeat de agente de cámaras",
            # Tarjeta virtual y BLE (residente)
            ("POST", "/api/v1/tv/mi-tarjeta-virtual/activar"):    "Activó tarjeta virtual",
            ("POST", "/api/v1/tv/mi-tarjeta-virtual/suspender"):  "Suspendió tarjeta virtual",
            ("POST", "/api/v1/tv/mi-tarjeta-virtual/reactivar"):  "Reactivó tarjeta virtual",
            ("POST", "/api/v1/ble/mi-ble/activar"):       "Activó credencial BLE",
            ("POST", "/api/v1/ble/mi-ble/suspender"):     "Suspendió credencial BLE",
            ("POST", "/api/v1/ble/mi-ble/reactivar"):     "Reactivó credencial BLE",
            ("POST", "/api/v1/ble/mi-ble/registrar-uso"): "Registró uso BLE",
            # Dispositivos FCM
            ("POST", "/api/v1/dispositivos/registrar"):    "Registró dispositivo para notificaciones",
            ("POST", "/api/v1/dispositivos/desregistrar"): "Desregistró dispositivo de notificaciones",
            ("POST", "/api/v1/dispositivos/probar-notificacion"): "Probó notificación push",
            # Recibos
            ("PUT",  "/api/v1/recibos/config"):            "Editó configuración de recibos",
            # Inventario
            ("POST", "/api/v1/inventario/tipos"):          "Creó tipo de artículo (inventario)",
            # Desarrollador
            ("POST", "/api/v1/dev/accesos-fisicos"):       "Creó acceso físico (dev)",
            ("POST", "/api/v1/dev/dispositivos"):          "Creó dispositivo Pi (dev)",
            ("POST", "/api/v1/dev/residenciales"):         "Creó residencial (dev)",
            # WebAuthn
            ("POST", "/api/v1/webauthn/registro/iniciar"):   "Inició registro de llave de seguridad",
            ("POST", "/api/v1/webauthn/registro/completar"): "Completó registro de llave de seguridad",
            ("POST", "/api/v1/webauthn/login/iniciar"):      "Inició login con llave de seguridad",
            ("POST", "/api/v1/webauthn/login/completar"):    "Completó login con llave de seguridad",
        }

        key = (m, e)
        if key in mapa_exacto:
            return mapa_exacto[key]

        # ── Mapeo por prefijo (endpoints con UUID dinámico) ────────
        # Orden: más específico primero
        prefijos = [
            # Auth - sesiones
            ("POST", "/api/v1/auth/sesiones/",    "/cerrar",             "Cerró sesión en otro dispositivo"),
            # Caja
            ("POST", "/api/v1/caja/descuadres/",  "/resolver",           "Resolvió descuadre de caja"),
            ("POST", "/api/v1/caja/salidas/",     "/autorizar",          "Autorizó salida de caja"),
            # Cuotas y pagos
            ("POST", "/api/v1/cuotas/mias/",      "/pagar",              "Subió comprobante de pago"),
            ("POST", "/api/v1/cuotas/abonos/",    "/pagar",              "Subió comprobante de abono"),
            ("POST", "/api/v1/cuotas/pagos/",     "/revisar",            "Revisó pago (aprobar/rechazar)"),
            # Cuentas
            ("PUT",  "/api/v1/cuentas/cuentas/",  None,                  "Editó cuenta/casa"),
            ("PUT",  "/api/v1/cuentas/unidades/",  None,                 "Editó unidad"),
            ("POST", "/api/v1/cuentas/cuentas/",  "/baja",               "Dio de baja cuenta"),
            ("POST", "/api/v1/cuentas/cuentas/",  "/nivelar-saldo",      "Niveló saldo de cuenta"),
            ("POST", "/api/v1/cuentas/cuentas/",  "/reactivar",          "Reactivó cuenta"),
            ("POST", "/api/v1/cuentas/cuentas/",  "/residentes",         "Agregó miembro a cuenta"),
            ("DELETE","/api/v1/cuentas/cuentas/",  "/residentes/",       "Quitó miembro de cuenta"),
            ("POST", "/api/v1/cuentas/cuentas/",  "/regenerar-enlace",   "Regeneró enlace de activación"),
            ("POST", "/api/v1/cuentas/cuentas/",  "/tarjetas",           "Asignó tarjeta a cuenta"),
            ("PUT",  "/api/v1/cuentas/tarifas/",  None,                  "Editó tarifa"),
            ("DELETE","/api/v1/cuentas/tarifas/",  None,                 "Desactivó tarifa"),
            ("POST", "/api/v1/cuentas/enrolamiento/generar", None,       "Generó código de enrolamiento"),
            ("DELETE","/api/v1/cuentas/enrolamiento/", None,             "Eliminó código de enrolamiento"),
            ("POST", "/api/v1/cuentas/solicitudes-baja/", "/resolver",   "Resolvió solicitud de baja"),
            # Usuarios
            ("POST", "/api/v1/usuarios/",         "/reset-password",     "Reseteó contraseña de usuario"),
            ("PUT",  "/api/v1/usuarios/",         None,                  "Editó usuario"),
            # Guardias (crear)
            ("POST", "/api/v1/guardias",          None,                  "Creó usuario guardia"),
            # Visitas
            ("POST", "/api/v1/visitas/",          "/cancelar",           "Canceló visita"),
            ("POST", "/api/v1/visitas/",          None,                  "Generó código QR de visita"),
            # Acceso
            ("PUT",  "/api/v1/acceso/puntos/",    None,                  "Editó punto de acceso"),
            # Arreglos de pago
            ("POST", "/api/v1/arreglos/",         "/cobrar",             "Cobró abono de arreglo"),
            ("POST", "/api/v1/arreglos/",         "/cancelar",           "Canceló arreglo de pago"),
            ("POST", "/api/v1/arreglos",          None,                  "Creó arreglo de pago"),
            # Cámaras
            ("PUT",  "/api/v1/camaras/",          None,                  "Editó cámara"),
            ("DELETE","/api/v1/camaras/",         None,                  "Eliminó cámara"),
            ("POST", "/api/v1/camaras/",          "/probar",             "Probó conexión de cámara"),
            # Comunicados
            ("POST", "/api/v1/comunicados",       None,                  "Publicó comunicado"),
            ("DELETE","/api/v1/comunicados/",     None,                  "Eliminó comunicado"),
            # Inventario
            ("PUT",  "/api/v1/inventario/tipos/",  None,                 "Editó tipo de artículo"),
            ("POST", "/api/v1/inventario/tipos/", "/stock",              "Agregó stock (inventario)"),
            # Dev
            ("PUT",  "/api/v1/dev/accesos-fisicos/",  None,              "Editó acceso físico (dev)"),
            ("DELETE","/api/v1/dev/accesos-fisicos/",  None,             "Eliminó acceso físico (dev)"),
            ("PUT",  "/api/v1/dev/dispositivos/",  None,                 "Editó dispositivo Pi (dev)"),
            ("POST", "/api/v1/dev/dispositivos/", "/regenerar-token",    "Regeneró token de Pi (dev)"),
            ("DELETE","/api/v1/dev/dispositivos/",  None,                "Eliminó dispositivo Pi (dev)"),
            # WebAuthn
            ("DELETE","/api/v1/webauthn/credenciales/", None,            "Eliminó llave de seguridad"),
        ]

        for entry in prefijos:
            met, prefix, suffix, desc = entry
            if m != met:
                continue
            if not e.startswith(prefix):
                continue
            if suffix is None:
                return desc
            if suffix in e[len(prefix):]:
                return desc

        # ── Fallback legible ───────────────────────────────────────
        accion = {"GET": "Consultó", "POST": "Ejecutó", "PUT": "Actualizó",
                  "DELETE": "Eliminó", "PATCH": "Modificó"}.get(m, m)
        ruta = e.replace("/api/v1/", "").replace("/", " › ")
        return f"{accion} {ruta}"

    def to_dict(self):
        return {
            "id":           self.id,
            "email":        self.email or "—",
            "rol":          self.rol or "—",
            "metodo":       self.metodo,
            "endpoint":     self.endpoint,
            "descripcion":  self.descripcion(),
            "status_code":  self.status_code,
            "ip":           self.ip,
            "created_at":   self.created_at.isoformat() if self.created_at else None,
        }
