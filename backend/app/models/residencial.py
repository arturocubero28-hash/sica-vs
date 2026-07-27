"""
Modelo de Residencial — la unidad de cliente/facturación para el futuro SaaS.

DISEÑO ACORDADO CON EL USUARIO (Día 37, sesión de bases multi-residencial):
  - Un admin = una Residencial = un cliente que factura. No es una tabla
    separada de "tenants" con su propia jerarquía compleja — es simplemente
    el admin dueño con un nombre y un logo configurables, y todo lo que ese
    admin (o su/s supervisor/es) crean cuelga de esa misma Residencial.
  - Hoy, en Villas del Sol, existe UNA sola fila acá — el comportamiento del
    sistema no cambia en nada porque todo sigue resolviendo al mismo valor.
  - El día que haya un segundo cliente, se crea una segunda fila con su
    propio admin, y el filtrado por residencial_id (ya presente en Usuario,
    Unidad, AccesoFisico y Dispositivo) empieza a separar los datos de
    verdad, sin haber tenido que tocar esas tablas de nuevo.

Quién pertenece a esta Residencial:
  - El admin dueño (Usuario.residencial_id apunta acá, igual que el resto)
  - Todo lo que ese admin o sus supervisores creen (guardias, cajeros,
    residentes, unidades, puntos de acceso, dispositivos Pi) hereda el
    mismo residencial_id al momento de crearse — ver cada endpoint de
    creación para el detalle de la herencia.

Quién NO pertenece a ninguna Residencial (residencial_id queda NULL):
  - super_admin y desarrollador: son roles a nivel de la plataforma SaaS,
    no de un cliente específico.
"""
import uuid
import datetime as dt

from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.extensions import db

# Día 47 — colores personalizables. Estos son los mismos valores que ya
# tenía el CSS por defecto (var(--marca-azul)/var(--marca-naranja)) antes
# de que existiera la personalización — una residencial que nunca elige sus
# propios colores ve exactamente lo mismo que veía antes de este cambio.
DEFAULT_COLOR_PRIMARIO = "#022E45"
DEFAULT_COLOR_SECUNDARIO = "#F48723"


class Residencial(db.Model):
    __tablename__ = "residenciales"

    id = db.Column(db.BigInteger, primary_key=True)
    uuid_publico = db.Column(PG_UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4)
    # El admin dueño — una Residencial tiene exactamente un admin raíz.
    # Los supervisores que ese admin cree tienen el mismo residencial_id,
    # pero NO son el "admin_id" de la Residencial (no pueden, por ejemplo,
    # transferir la propiedad ni crear otros supervisores — ver
    # app/utils/passwords.py puede_gestionar_rol()).
    admin_id = db.Column(db.BigInteger, db.ForeignKey("usuarios.id"), unique=True, nullable=False)
    nombre = db.Column(db.String(160), nullable=False)
    # Datos de contacto del cliente (Día 37, flujo 'crear nueva residencial').
    # Nullable a nivel de base a propósito — la residencial de Villas del
    # Sol ya existía antes de estos campos y no los tiene cargados. Para
    # residenciales NUEVAS, la obligatoriedad se exige en el endpoint de
    # creación (crear_residencial), no como constraint de base de datos.
    direccion = db.Column(db.String(255))
    telefono = db.Column(db.String(30))
    logo_archivo = db.Column(db.String(255))  # nombre de archivo guardado (mismo patrón que comunicados/comprobantes)
    # Día 47 — colores personalizables. Formato hex ("#022E45"), validado en
    # el endpoint de escritura, no como constraint de base (mismo criterio
    # que el resto de este modelo: la obligatoriedad/formato se exige al
    # escribir, no a nivel de columna). NULL = usa el valor por defecto de
    # fábrica (ver DEFAULT_COLOR_PRIMARIO/SECUNDARIO más abajo) — así una
    # residencial que nunca toca esto no tiene que tener nada guardado.
    color_primario = db.Column(db.String(7))    # el azul, el que más resalta
    color_secundario = db.Column(db.String(7))  # el naranja, de acento
    activa = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), default=dt.datetime.utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=dt.datetime.utcnow,
                           onupdate=dt.datetime.utcnow)

    admin = db.relationship("Usuario", foreign_keys=[admin_id], lazy="joined")

    def to_dict(self, incluir_stats=False):
        d = {
            "id": str(self.uuid_publico),
            "nombre": self.nombre,
            "direccion": self.direccion,
            "telefono": self.telefono,
            "logo_archivo": self.logo_archivo,
            # Día 47: siempre se devuelve un color EFECTIVO (el elegido, o
            # el de fábrica si nunca se personalizó) — el frontend nunca
            # tiene que lidiar con null ni duplicar el valor por defecto.
            "color_primario": self.color_primario or DEFAULT_COLOR_PRIMARIO,
            "color_secundario": self.color_secundario or DEFAULT_COLOR_SECUNDARIO,
            "activa": self.activa,
            "admin": {
                "nombre": f"{self.admin.nombre} {self.admin.apellido}",
                "email": self.admin.email,
            } if self.admin else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if incluir_stats:
            from app.models.usuario import Usuario
            from app.models.dispositivo import Dispositivo
            d["stats"] = {
                "guardias": Usuario.query.filter_by(residencial_id=self.id, rol="guardia").count(),
                "cajeros": Usuario.query.filter_by(residencial_id=self.id, rol="cajero").count(),
                "supervisores": Usuario.query.filter_by(residencial_id=self.id, rol="supervisor").count(),
                "residentes": Usuario.query.filter_by(residencial_id=self.id, rol="residente").count(),
                "dispositivos": Dispositivo.query.filter_by(residencial_id=self.id).count(),
            }
        return d
