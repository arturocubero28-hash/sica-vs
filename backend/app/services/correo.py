"""
Envío de correos transaccionales con Resend (Día 61).

Hasta hoy, tanto la activación de cuentas de residentes como la
recuperación de contraseña quedaban a medio hacer en producción: el
diseño (correcto, por seguridad) omite el token de activación en la
respuesta de la API en producción -- el token DEBE llegar solo por
correo, directo al residente, para que nadie con acceso al panel de
admin pueda activar cuentas ajenas. Pero el envío de correo en sí nunca
se había implementado (quedaba como TODO), así que el link nunca le
llegaba a nadie por ningún lado.

Todas las funciones de este módulo son best-effort: si Resend no está
configurado (RESEND_API_KEY vacío) o la llamada falla, se registra el
error en el log pero NUNCA se relanza la excepción -- un correo que no
sale no debe tumbar la operación que lo originó (crear una cuenta,
pedir un reset), igual criterio que ya se usa en todo el proyecto para
las notificaciones push.
"""
import logging

logger = logging.getLogger(__name__)


def _resend_configurado():
    from flask import current_app
    return bool(current_app.config.get("RESEND_API_KEY"))


def _registrar_envio(destinatario, resend_id):
    """
    Día 72 — deja anotado en el usuario que se le mandó un correo y con qué
    id lo identifica Resend.

    El id es la pieza que después permite casar el webhook ("el correo
    tal rebotó") con la persona correcta, incluso si mientras tanto le
    cambiaron la dirección. Es best-effort como todo este módulo: si algo
    falla, el correo ya salió y eso es lo que importa.
    """
    try:
        from app.extensions import db
        from app.models.usuario import Usuario
        import datetime as dt
        u = Usuario.query.filter_by(email=(destinatario or "").strip().lower()).first()
        if not u:
            return
        u.correo_estado = "enviado"
        u.correo_detalle = None
        u.correo_resend_id = resend_id
        u.correo_actualizado = dt.datetime.now(dt.timezone.utc)
        db.session.commit()
    except Exception:
        logger.exception("No se pudo registrar el envío de correo a %s", destinatario)
        try:
            from app.extensions import db
            db.session.rollback()
        except Exception:
            pass


def _enviar_crudo(destinatario, asunto, html):
    """
    Manda el correo y devuelve (ok, resend_id). Nunca lanza excepción.

    Día 73 — separado de _enviar porque la verificación de correo necesita
    el id del envío SIN atarlo a un usuario: todavía no existe, de eso se
    trata. _enviar lo usa y además lo registra en el usuario.
    """
    if not _resend_configurado():
        logger.warning(
            "RESEND_API_KEY no configurado -- correo NO enviado a %s (asunto: %s)",
            destinatario, asunto,
        )
        return False, None
    try:
        import resend
        from flask import current_app
        resend.api_key = current_app.config["RESEND_API_KEY"]
        remitente = current_app.config.get(
            "RESEND_FROM",
            "Residencial Villas del Sol <notificaciones@patronatovillasdelsol.com>")
        respuesta = resend.Emails.send({
            "from": remitente,
            "to": destinatario,
            "subject": asunto,
            "html": html,
        })
        # Resend responde con el id del envío. Es lo que trae el webhook,
        # así que es lo que permite casar el aviso con quien corresponde.
        resend_id = None
        if isinstance(respuesta, dict):
            resend_id = respuesta.get("id")
        elif respuesta is not None:
            resend_id = getattr(respuesta, "id", None)
        return True, resend_id
    except Exception:
        logger.exception("Error enviando correo a %s (asunto: %s)", destinatario, asunto)
        return False, None


def _enviar(destinatario, asunto, html):
    """Envío de bajo nivel. Devuelve True/False, nunca lanza excepción."""
    ok, resend_id = _enviar_crudo(destinatario, asunto, html)
    if ok:
        _registrar_envio(destinatario, resend_id)
    return ok


def _plantilla_base(titulo, cuerpo_html, nombre_residencial, boton_texto=None, boton_url=None):
    """
    Plantilla HTML simple y compatible con la mayoría de clientes de
    correo (sin CSS externo ni JS -- Gmail/Outlook/etc. los descartan).
    Día 72 — el encabezado muestra el nombre de la residencial, no "SICA-VS".
    Ese era el nombre interno del proyecto y ya no se usa de cara a nadie:
    la app se llama "Residencial Villas del Sol App". Poner acá el nombre de
    la residencial además sirve para cualquier otra que use el sistema.

    Usa el naranja/azul de marca como base; no usa el color
    dinámico de cada residencial acá a propósito -- a diferencia de los
    PDFs (que se abren DESPUÉS de haber iniciado sesión, con la
    residencial ya identificada), este correo es lo PRIMERO que ve un
    residente, antes incluso de tener sesión -- más simple y confiable
    usar la marca fija de la plataforma.
    """
    boton_html = ""
    respaldo_html = ""
    if boton_texto and boton_url:
        boton_html = f"""
        <tr><td style="padding: 24px 0;">
          <a href="{boton_url}" style="background:#F48723;color:#ffffff;text-decoration:none;
             padding:14px 32px;border-radius:10px;font-weight:600;font-size:15px;
             display:inline-block;">{boton_texto}</a>
        </td></tr>"""
        # Día 73 — el "si el botón no funciona" solo tiene sentido si hay
        # botón. El correo de verificación no lleva, y ahí quedaba la frase
        # colgando con un enlace vacío.
        respaldo_html = f"""
            <p style="color:#93a0ad;font-size:12px;margin-top:24px;">
              Si el botón no funciona, copiá y pegá este enlace en tu navegador:<br/>
              <span style="word-break:break-all;">{boton_url}</span>
            </p>"""
    return f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f7fb;padding:32px 0;">
      <tr><td align="center">
        <table role="presentation" width="480" cellpadding="0" cellspacing="0"
               style="background:#ffffff;border-radius:16px;overflow:hidden;font-family:Arial,sans-serif;">
          <tr><td style="background:#022E45;padding:24px 32px;">
            <span style="color:#ffffff;font-size:20px;font-weight:700;">{nombre_residencial}</span>
          </td></tr>
          <tr><td style="padding:32px;">
            <h2 style="color:#022E45;margin:0 0 16px;font-size:19px;">{titulo}</h2>
            <div style="color:#3a4048;font-size:14.5px;line-height:1.6;">{cuerpo_html}</div>
            {boton_html}{respaldo_html}
          </td></tr>
        </table>
      </td></tr>
    </table>"""


def _bloque_descarga_app():
    """
    Sección de "descargá nuestra app" para el correo de activación (Día 62,
    pedido del usuario). Android apunta al APK real (mismo archivo que ya
    se sirve desde la landing page); iOS se menciona como "próximamente" en
    vez de mostrar un link a la App Store que todavía no existe -- evita
    que un residente haga clic en un enlace roto. Cuando la app se publique
    en la App Store, solo hace falta cambiar esa línea acá.
    """
    from flask import current_app
    url_frontend = current_app.config.get("FRONTEND_URL", "https://patronatovillasdelsol.com")
    url_apk = f"{url_frontend}/descargas/sicavs.apk"
    return f"""
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:20px;">
        <tr><td style="border-top:1px solid #eeede8;padding-top:16px;">
          <p style="color:#3a4048;font-size:13.5px;margin:0 0 8px;">
            También podés descargar nuestra aplicación móvil:
          </p>
          <a href="{url_apk}" style="color:#F48723;font-size:13.5px;font-weight:600;text-decoration:none;">
            Descargar para Android
          </a>
          <span style="color:#93a0ad;font-size:12.5px;"> · Próximamente en App Store (iOS)</span>
        </td></tr>
      </table>"""


def _correo_activacion(nombre, token, nombre_residencial, es_reenvio=False):
    """Devuelve (asunto, html) del correo con el enlace para definir la contraseña."""
    from flask import current_app
    url_frontend = current_app.config.get("FRONTEND_URL", "https://patronatovillasdelsol.com")
    url = f"{url_frontend}/?activar={token}"

    # Día 62 — usa el nombre real de la persona y el de SU residencial.
    saludo = f"Hola {nombre}," if nombre else "Hola,"
    intro = (
        f"{saludo} te reenviamos tu enlace de activación." if es_reenvio else
        f"{saludo} fuiste registrado/a como residente de "
        f"<b>{nombre_residencial}</b>."
    )
    cuerpo = f"""
      <p>{intro}</p>
      <p>Hacé clic en el botón de abajo para confirmar tu cuenta y definir tu contraseña.</p>
      <p style="color:#93a0ad;font-size:13px;">Este enlace vence en 48 horas.</p>
      {_bloque_descarga_app()}"""
    html = _plantilla_base(
        "Activá tu cuenta" if not es_reenvio else "Tu nuevo enlace de activación",
        cuerpo, nombre_residencial, "Confirmar mi cuenta", url,
    )
    return f"Activá tu cuenta — {nombre_residencial}", html


def enviar_correo_activacion(email, nombre, token, nombre_residencial, es_reenvio=False):
    """Correo con el link para que un residente defina su contraseña."""
    asunto, html = _correo_activacion(nombre, token, nombre_residencial, es_reenvio)
    return _enviar(email, asunto, html)


def enviar_activacion_antes_de_crear(email, nombre, token, nombre_residencial):
    """
    Día 73 — el correo de activación que TAMBIÉN sirve de verificación.
    Devuelve (ok, resend_id).

    Se manda ANTES de crear la cuenta, y con el id que devuelve Resend se
    espera la confirmación de entrega. Recién si llega se crea la cuenta.

    Funciona porque el enlace no depende de que la cuenta exista cuando se
    manda: lleva el correo adentro (un JWT firmado) y la cuenta se busca
    recién cuando la persona hace clic. Así la persona recibe un solo
    correo, y si la dirección no existe no se creó nada.

    No se registra en el usuario (todavía no existe): lo hace el endpoint
    que crea la cuenta, copiando el id desde la verificación.
    """
    asunto, html = _correo_activacion(nombre, token, nombre_residencial)
    return _enviar_crudo(email, asunto, html)


def enviar_correo_reset(email, token, nombre_residencial):
    """Correo con el link para restablecer una contraseña olvidada."""
    from flask import current_app
    url_frontend = current_app.config.get("FRONTEND_URL", "https://patronatovillasdelsol.com")
    url = f"{url_frontend}/?reset={token}"
    cuerpo = f"""
      <p>Pediste restablecer tu contraseña de <b>{nombre_residencial}</b>.</p>
      <p>Hacé clic en el botón de abajo para elegir una nueva. Si vos no pediste esto,
      podés ignorar este correo con tranquilidad -- tu contraseña actual sigue funcionando.</p>
      <p style="color:#93a0ad;font-size:13px;">Este enlace vence en 2 horas.</p>"""
    html = _plantilla_base("Restablecer contraseña", cuerpo, nombre_residencial,
                           "Restablecer contraseña", url)
    return _enviar(email, f"Restablecer tu contraseña — {nombre_residencial}", html)
