"""
Utilidades compartidas de contraseñas y jerarquía de roles.

SEC-01 (Auditoría Día 35): antes, guardias/cajeros/desarrolladores nuevos
recibían todos la misma contraseña fija 'VillasDelSol2026', y cualquier
admin podía resetear la contraseña de cualquier otro usuario sin importar
su rol — incluyendo a un super_admin o desarrollador.

Diseño acordado con el usuario:
  - Guardias y cajeros son "usuarios locales de papel": el admin genera
    una contraseña aleatoria, se la muestra en pantalla una sola vez para
    anotarla y entregársela en persona. Deben cambiarla en su primer
    login. NO tienen recuperación por correo (no la necesitan / no usan
    email activo para esto).
  - Residentes, admin y super_admin siguen usando el flujo existente de
    recuperación por correo (sin cambios en este trabajo).
  - Un admin no puede crear ni resetear un super_admin o desarrollador —
    eso queda reservado a super_admin.

BASES MULTI-RESIDENCIAL (Día 37): se agrega el rol 'supervisor' — mismo
nivel de acceso operativo que 'admin' en toda la aplicación (ver
app/auth/security.py roles_required, que trata a 'supervisor' como
equivalente a 'admin' en cualquier endpoint que acepte ese rol), pero con
dos restricciones que SOLO admin/super_admin pueden saltarse:
  - Un supervisor no puede crear ni gestionar a OTRO supervisor.
  - Un supervisor no puede gestionar al admin dueño de la residencial.
Esto evita que un supervisor se auto-promueva o le quite el control al
admin, mientras le da autonomía real para todo lo demás (guardias,
cajeros, residentes, unidades, dispositivos).
"""
import secrets
import string


def generar_password_temporal(largo: int = 10) -> str:
    """
    Genera una contraseña aleatoria que cumple la política mínima del
    sistema (>= 8 caracteres, al menos una mayúscula, al menos un signo)
    de forma garantizada — no por azar.

    Se arma explícitamente con una mayúscula + un signo + relleno
    alfanumérico, y se mezcla, para no depender de que salgan por
    casualidad en una generación puramente aleatoria.
    """
    mayusculas = string.ascii_uppercase
    minusculas = string.ascii_lowercase
    digitos = string.digits
    signos = "!@#$%&*"

    # Garantizar al menos un carácter de cada categoría requerida
    obligatorios = [
        secrets.choice(mayusculas),
        secrets.choice(signos),
        secrets.choice(digitos),
    ]
    resto_alfabeto = mayusculas + minusculas + digitos
    relleno = [secrets.choice(resto_alfabeto) for _ in range(largo - len(obligatorios))]

    caracteres = obligatorios + relleno
    # Mezclar para que no siempre empiece con mayúscula-signo-dígito
    for i in range(len(caracteres) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        caracteres[i], caracteres[j] = caracteres[j], caracteres[i]

    return "".join(caracteres)


# Jerarquía de roles: valor más alto = más privilegio.
# Un usuario solo puede crear/resetear roles con jerarquía MENOR a la suya.
# 'supervisor' queda al mismo nivel que 'admin' (2) — la distinción entre
# ambos no se resuelve por jerarquía numérica sino por la regla especial
# de puede_gestionar_rol() de abajo, porque "mismo nivel" normalmente
# significa "no se pueden gestionar entre sí" (2 > 2 es falso), que es
# exactamente lo que queremos para supervisor↔supervisor y
# supervisor↔admin, pero NO para admin creando un supervisor por primera
# vez — ese caso puntual se resuelve aparte.
_JERARQUIA = {
    "residente": 0,
    "cajero": 1,
    "guardia": 1,
    "supervisor": 2,
    "admin": 2,
    "super_admin": 3,
    "desarrollador": 3,
}


def puede_gestionar_rol(rol_actor: str, rol_objetivo: str) -> bool:
    """
    ¿Un usuario con rol_actor puede crear/resetear/editar credenciales de
    un usuario con rol_objetivo?

    Regla general: estrictamente menor jerarquía. Un admin (2) puede
    gestionar guardia/cajero (1) y residente (0), pero NO otro admin (2)
    ni super_admin/desarrollador (3). Solo super_admin/desarrollador
    pueden gestionar admins entre sí.

    Regla especial para 'supervisor' (Día 37, bases multi-residencial):
      - Gestionar a un supervisor (crearlo, resetearlo, editarlo) es
        exclusivo de admin/super_admin — ni siquiera OTRO supervisor
        puede hacerlo, aunque comparta la misma jerarquía numérica.
      - Un supervisor, como ACTOR, gestiona todo lo demás (guardia,
        cajero, residente) exactamente igual que un admin.
    """
    if rol_objetivo == "supervisor":
        return rol_actor in ("admin", "super_admin")
    if rol_actor == "supervisor":
        return _JERARQUIA.get("admin", -1) > _JERARQUIA.get(rol_objetivo, 99)
    return _JERARQUIA.get(rol_actor, -1) > _JERARQUIA.get(rol_objetivo, 99)


# Roles que reciben contraseña de papel (sin recuperación por correo).
ROLES_CREDENCIAL_LOCAL = {"guardia", "cajero"}
