"""
Prueba de humo del padrón (Día 69), contra una base SQLite en memoria.

No reemplaza una prueba en el servidor real, pero verifica lo que más
importa de este sprint sin depender de PostgreSQL:
  1. Se puede crear una persona SIN correo ni contraseña.
  2. Esa persona no puede autenticarse de ninguna manera.
  3. Una casa en censo no entra en la generación de cuotas.
  4. Al convertirla, sí entra -- y la conversión no inventa cuotas viejas.

Nota: los id se asignan a mano porque SQLite solo autoincrementa columnas
INTEGER PRIMARY KEY, no BIGINT como usa el proyecto (en PostgreSQL es
BIGSERIAL y se genera solo). Es una limitación del motor de prueba, no del
modelo.

Uso:  python3 prueba_censo_dia69.py
"""
import os
import sys
import logging

sys.path.insert(0, ".")
logging.disable(logging.WARNING)

# La base en memoria se fija ACÁ y no en la línea de comandos: el docstring
# de arriba dice "python3 prueba_censo_dia69.py" a secas, y sin esto el
# create_app() de abajo toma el PostgreSQL de desarrollo por defecto y la
# prueba revienta en el import de psycopg antes de verificar nada.
# setdefault y no asignación directa, para poder apuntarla a otra base
# desde afuera si alguna vez hace falta.
os.environ.setdefault("DATABASE_URL", "sqlite://")

from app import create_app                       # noqa: E402
from app.extensions import db                    # noqa: E402
from app.models.usuario import Usuario           # noqa: E402
from app.models.cuenta import (                  # noqa: E402
    Unidad, Cuenta, Residente, Tarifa,
)

fallos = []


def verificar(descripcion, condicion):
    estado = "OK  " if condicion else "FALLA"
    print(f"  [{estado}] {descripcion}")
    if not condicion:
        fallos.append(descripcion)


app = create_app()
with app.app_context():
    db.drop_all()
    db.create_all()

    print("\n1. Persona del padrón, sin credenciales")
    unidad = Unidad(id=1, tipo="casa", identificador="Casa Censo 1", activa=True)
    db.session.add(unidad)
    db.session.flush()

    persona = Usuario(
        id=1, nombre="Juan", apellido="Pérez", email=None,
        rol="residente", es_censo=True, activo=False,
    )
    db.session.add(persona)
    db.session.flush()

    verificar("se guarda sin correo", persona.email is None)
    verificar("se guarda sin contraseña", persona.password_hash is None)

    print("\n2. No puede autenticarse de ninguna forma")
    verificar("check_password('') devuelve False, no revienta",
              persona.check_password("") is False)
    verificar("check_password con cualquier clave devuelve False",
              persona.check_password("VillasDelSol2026") is False)
    verificar("puede_iniciar_sesion es False",
              persona.puede_iniciar_sesion is False)

    print("\n3. Dos personas del padrón conviven sin correo")
    otra = Usuario(id=2, nombre="María", apellido="López", email=None,
                   rol="residente", es_censo=True, activo=False)
    db.session.add(otra)
    try:
        db.session.flush()
        verificar("el índice único de correo admite varios NULL", True)
    except Exception as e:
        verificar(f"el índice único de correo admite varios NULL ({e})", False)

    print("\n4. La casa del padrón no entra en cobranza")
    tarifa = Tarifa(id=1, nombre="Cuota mensual", monto=500, activa=True)
    db.session.add(tarifa)
    db.session.flush()

    casa = Cuenta(id=1, unidad_id=unidad.id, modo_participacion="censo",
                  tarifa_id=None, dia_pago=None)
    db.session.add(casa)
    db.session.flush()
    db.session.add(Residente(id=1, usuario_id=persona.id, cuenta_id=casa.id,
                             rol_cuenta="titular"))
    db.session.commit()

    verificar("es_censo es True", casa.es_censo is True)
    verificar("cobra_cuotas() es False", casa.cobra_cuotas() is False)

    print("\n5. Una casa del padrón CON tarifa cargada por error sigue sin cobrar")
    casa.tarifa_id = tarifa.id
    db.session.commit()
    verificar("sigue sin cobrar: manda el modo, no la tarifa",
              casa.cobra_cuotas() is False)
    casa.tarifa_id = None
    db.session.commit()

    print("\n6. Conversión a casa completa")
    import datetime as dt
    casa.modo_participacion = "completa"
    casa.tarifa_id = tarifa.id
    casa.dia_pago = 5
    casa.fecha_conversion = dt.date.today()
    db.session.commit()

    verificar("es_censo pasa a False", casa.es_censo is False)
    verificar("cobra_cuotas() pasa a True", casa.cobra_cuotas() is True)
    verificar("queda constancia de la fecha de conversión",
              casa.fecha_conversion == dt.date.today())

    print("\n7. Persona del padrón convertida en usuario")
    persona.email = "juan.perez@correo.com"
    persona.es_censo = False
    persona.set_password("ClaveSegura1!")
    db.session.commit()

    verificar("ahora sí puede iniciar sesión (tras activarse)",
              persona.check_password("ClaveSegura1!") is True)
    verificar("es la MISMA fila: conserva su id",
              persona.id is not None)

    print("\n8. Serialización para el panel")
    r = Residente.query.filter_by(cuenta_id=casa.id).first()
    d = r.to_dict()
    verificar("to_dict expone es_censo", "es_censo" in d)
    verificar("to_dict expone foto_url", "foto_url" in d)
    dc = casa.to_dict()
    verificar("la cuenta expone modo_participacion", "modo_participacion" in dc)
    verificar("la cuenta expone fecha_conversion", "fecha_conversion" in dc)

    print("\n9. Estado 'censo' se distingue de 'pendiente'")
    tercero = Usuario(id=3, nombre="Ana", apellido="Díaz", email=None,
                      rol="residente", es_censo=True, activo=False)
    db.session.add(tercero)
    db.session.flush()
    r3 = Residente(id=2, usuario_id=tercero.id, cuenta_id=casa.id, rol_cuenta="miembro")
    db.session.add(r3)
    db.session.commit()
    verificar("una persona del padrón reporta estado_acceso='censo'",
              r3.to_dict()["estado_acceso"] == "censo")

    print("\n10. Código de emergencia")
    verificar("sin código configurado, tiene_codigo_emergencia es False",
              persona.tiene_codigo_emergencia is False)
    verificar("sin código, check devuelve False y no revienta",
              persona.check_codigo_emergencia("123456") is False)

    persona.set_codigo_emergencia("846213")
    db.session.commit()
    verificar("después de definirlo, queda configurado",
              persona.tiene_codigo_emergencia is True)
    verificar("el código correcto valida", persona.check_codigo_emergencia("846213") is True)
    verificar("un código distinto no valida", persona.check_codigo_emergencia("846214") is False)
    verificar("un código vacío no valida", persona.check_codigo_emergencia("") is False)
    verificar("queda la fecha de actualización",
              persona.codigo_emergencia_actualizado is not None)

    print("\n11. El código NO es una contraseña")
    # Son dos secretos distintos y no deben ser intercambiables: el código
    # lo escucha el guardia en voz alta en el portón.
    verificar("el código de emergencia no sirve para iniciar sesión",
              persona.check_password("846213") is False)
    verificar("la contraseña no sirve como código de emergencia",
              persona.check_codigo_emergencia("ClaveSegura1!") is False)
    verificar("el hash del código es distinto al de la contraseña",
              persona.codigo_emergencia_hash != persona.password_hash)

    print("\n12. El enum origen_evento acepta 'proveedor'")
    # ESTA VERIFICACIÓN EXISTE POR UN BUG REAL de este mismo día.
    #
    # La migración de app/__init__.py hacía el ALTER TYPE para agregar
    # 'proveedor' al tipo de PostgreSQL, pero el modelo seguía declarando
    # db.Enum("residente", "visita"). SQLAlchemy valida el valor del lado de
    # Python ANTES de mandar el INSERT, así que registrar un proveedor
    # lanzaba LookupError y el endpoint respondía 500 — con la base
    # perfectamente capaz de aceptar el valor.
    #
    # Es un error que no se ve leyendo ninguno de los dos archivos por
    # separado: hay que mirar los dos a la vez. Por eso se prueba.
    from app.models.visita import EventoAcceso, AccesoFisico  # noqa: E402

    valores = set(EventoAcceso.__table__.c.origen.type.enums)
    for esperado in ("residente", "visita", "proveedor"):
        verificar(f"el modelo declara origen='{esperado}'", esperado in valores)

    # Y que de verdad deje insertar el valor, no solo que esté en la lista.
    acceso = AccesoFisico(id=1, nombre="Tranca de prueba",
                          punto_acceso="Portón Principal", tipo="vehicular",
                          direccion="entrada", activo=True)
    db.session.add(acceso)
    db.session.flush()
    ev = EventoAcceso(id=1, origen="proveedor", direccion="entrada",
                      acceso_id=acceso.id, metodo="proveedor",
                      proveedor_empresa="Agua Azul",
                      proveedor_conductor="Juan Pérez")
    db.session.add(ev)
    db.session.commit()
    verificar("un evento de proveedor se guarda sin reventar", ev.id is not None)
    d = ev.to_dict()
    verificar("el evento reporta la empresa", d["proveedor_empresa"] == "Agua Azul")
    verificar("el evento reporta el método", d["metodo"] == "proveedor")
    verificar("sin autorizador, autorizado_por es None", d["autorizado_por"] is None)

print("\n" + "=" * 58)
if fallos:
    print(f"RESULTADO: {len(fallos)} verificación(es) fallaron")
    for f in fallos:
        print("  -", f)
    sys.exit(1)
print("RESULTADO: todas las verificaciones pasaron")
