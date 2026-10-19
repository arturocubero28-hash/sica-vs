"""
Modelo de ejemplo: Usuario.
Sirve como PATRÓN para que el equipo cree sus propios modelos.

Convenciones:
  * Cada modelo en su propio archivo dentro de app/models/
  * Siempre id, created_at, updated_at
  * uuid_publico para exponer en la API (nunca el id interno)
  * Método to_dict() para serializar de forma controlada
"""
import uuid
import datetime as dt
import bcrypt

from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.extensions import db


class Usuario(db.Model):
    __tablename__ = "usuarios"

    id = db.Column(db.BigInteger, primary_key=True)
    uuid_publico = db.Column(PG_UUID(as_uuid=True), unique=True, nullable=False,
                             default=uuid.uuid4)
    nombre = db.Column(db.String(120), nullable=False)
    apellido = db.Column(db.String(120), nullable=False)
    # Día 69 — opcional: una persona del padrón (censo) existe en el sistema
    # para que el guardia pueda identificarla, pero no tiene correo ni usa la
    # app. PostgreSQL admite varios NULL en un índice único, así que muchas
    # personas sin correo conviven sin chocar entre sí.
    email = db.Column(db.String(160), unique=True, nullable=True)
    telefono = db.Column(db.String(30))
    # Información extendida del residente (titular y dependientes)
    dni = db.Column(db.String(20))                        # número de identidad
    rtn = db.Column(db.String(20))                        # para recibos SAR (futuro)
    direccion_exacta = db.Column(db.String(255))          # dirección domiciliar completa
    profesion = db.Column(db.String(120))
    # Información laboral/educativa (requisito de la administración Día 29)
    ocupacion = db.Column(db.String(20))        # estudiante | profesional | otro
    centro_estudios = db.Column(db.String(160)) # si es estudiante
    lugar_trabajo = db.Column(db.String(160))   # si es profesional
    contacto_emergencia_nombre = db.Column(db.String(120))
    contacto_emergencia_telefono = db.Column(db.String(30))
    # Día 69 — opcional por la misma razón que el correo. Sin hash NO hay
    # forma de autenticarse: check_password() devuelve False siempre (ver
    # abajo) y el login rechaza antes de llegar ahí.
    password_hash = db.Column(db.String(255), nullable=True)
    # Marca explícita de persona del padrón sin acceso al sistema. Se prefiere
    # esta bandera a deducirlo de password_hash IS NULL, para que los listados
    # y conteos de usuarios puedan excluirlos sin depender de un nulo.
    es_censo = db.Column(db.Boolean, nullable=False, default=False)
    # Foto del miembro, capturada SOLO por administración (Día 68, pedido del
    # patronato). Es la que ve el guardia para verificar identidad, y la que
    # el residente ve en su perfil — en modo lectura: si el propio residente
    # pudiera cambiarla, la verificación del guardia dejaría de servir.
    foto_url = db.Column(db.String(255))
    # Día 69 — código de emergencia de 6 dígitos para entrar sin teléfono.
    # Hasheado como una contraseña: no se puede consultar, solo reemplazar.
    # Ver la nota larga en app/__init__.py sobre por qué existe.
    codigo_emergencia_hash = db.Column(db.String(255))
    codigo_emergencia_actualizado = db.Column(db.DateTime(timezone=True))
    # rol global: super_admin | admin | guardia | residente
    # ENUM real de PostgreSQL (rol_global) — fix Día 36.
    rol = db.Column(
        db.Enum("super_admin", "admin", "supervisor", "guardia", "residente", "cajero", "desarrollador",
                name="rol_global", create_type=False),
        nullable=False, default="residente")
    activo = db.Column(db.Boolean, nullable=False, default=True)
    debe_cambiar_password = db.Column(db.Boolean, nullable=False, default=False)
    biometria_activa = db.Column(db.Boolean, nullable=False, default=False)
    # Bases para multi-residencial (Día 37): a qué Residencial pertenece este
    # usuario. NULL para super_admin/desarrollador (roles de plataforma, no
    # de un cliente). Para el admin dueño, apunta a SU PROPIA Residencial
    # (se completa al crearla). Todo lo demás (guardia, cajero, supervisor,
    # residente) hereda este valor del admin/supervisor que lo creó — ver
    # cada endpoint de creación. Hoy, con un solo admin en Villas del Sol,
    # este campo tiene el mismo valor en todos lados y no cambia ningún
    # comportamiento existente.
    residencial_id = db.Column(db.BigInteger, db.ForeignKey("residenciales.id"))
    # Solo aplica a usuarios con rol 'guardia': en qué punto de acceso está
    # trabajando este turno (ej. "Portón Principal"). Se elige al iniciar
    # sesión y queda fijo — el guardia normalmente usa siempre el mismo
    # teléfono asignado a un punto específico (ACCESS-04, Auditoría Día 35).
    punto_acceso_actual = db.Column(db.String(80))
    ultimo_acceso = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=dt.datetime.utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=dt.datetime.utcnow,
                           onupdate=dt.datetime.utcnow)

    # ---- Manejo seguro de contraseñas (bcrypt) ----
    def set_password(self, password: str):
        self.password_hash = bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

    def check_password(self, password: str) -> bool:
        # Día 69 — guarda obligatoria: una persona del padrón no tiene hash.
        # Sin este chequeo, password_hash en nulo reventaba acá con un
        # AttributeError (None.encode) y el login devolvía un 500 en vez de
        # un rechazo limpio. Sin credenciales no hay autenticación posible.
        if not self.password_hash:
            return False
        return bcrypt.checkpw(
            password.encode("utf-8"), self.password_hash.encode("utf-8")
        )

    # ── Código de emergencia (Día 69) ──────────────────────────────────────
    def set_codigo_emergencia(self, codigo: str):
        """Guarda el código hasheado. Quien llama ya validó el formato."""
        import datetime as _dt
        self.codigo_emergencia_hash = bcrypt.hashpw(
            codigo.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")
        self.codigo_emergencia_actualizado = _dt.datetime.now(_dt.timezone.utc)

    def check_codigo_emergencia(self, codigo: str) -> bool:
        """
        Verifica el código de emergencia.

        OJO: este código NO sirve para iniciar sesión ni para nada más del
        sistema. Es solo para que el guardia encuentre a la persona cuando
        llega sin teléfono. La autorización real la da el guardia después de
        verificar la identificación contra la foto en ficha.
        """
        if not self.codigo_emergencia_hash or not codigo:
            return False
        return bcrypt.checkpw(
            codigo.encode("utf-8"), self.codigo_emergencia_hash.encode("utf-8")
        )

    @property
    def tiene_codigo_emergencia(self) -> bool:
        return bool(self.codigo_emergencia_hash)

    @property
    def puede_iniciar_sesion(self) -> bool:
        """
        True solo si esta persona tiene con qué autenticarse. Las personas
        del censo existen para que el guardia las identifique, no para entrar
        al sistema.
        """
        return bool(self.email) and bool(self.password_hash) and not self.es_censo

    # ---- Serialización para la API (nunca expone el hash ni el id interno) ----
    def to_dict(self):
        return {
            "id": str(self.uuid_publico),
            "nombre": self.nombre,
            "apellido": self.apellido,
            "email": self.email,
            "telefono": self.telefono,
            "dni": self.dni,
            "rtn": self.rtn,
            "direccion_exacta": self.direccion_exacta,
            "profesion": self.profesion,
            "ocupacion": self.ocupacion,
            "centro_estudios": self.centro_estudios,
            "lugar_trabajo": self.lugar_trabajo,
            "contacto_emergencia_nombre": self.contacto_emergencia_nombre,
            "contacto_emergencia_telefono": self.contacto_emergencia_telefono,
            "rol": self.rol,
            "activo": self.activo,
            "debe_cambiar_password": self.debe_cambiar_password,
            "biometria_activa": self.biometria_activa,
            "punto_acceso_actual": self.punto_acceso_actual,
        }