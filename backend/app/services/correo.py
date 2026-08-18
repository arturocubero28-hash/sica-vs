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


def _enviar(destinatario, asunto, html):
    """Envío de bajo nivel. Devuelve True/False, nunca lanza excepción."""
    if not _resend_configurado():
        logger.warning(
            "RESEND_API_KEY no configurado -- correo NO enviado a %s (asunto: %s)",
            destinatario, asunto,
        )
        return False
    try:
        import resend
        from flask import current_app
        resend.api_key = current_app.config["RESEND_API_KEY"]
        remitente = current_app.config.get(
            "RESEND_FROM", "SICA-VS <notificaciones@patronatovillasdelsol.com>")
        resend.Emails.send({
            "from": remitente,
            "to": destinatario,
            "subject": asunto,
            "html": html,
        })
        return True
    except Exception:
        logger.exception("Error enviando correo a %s (asunto: %s)", destinatario, asunto)
        return False


def _plantilla_base(titulo, cuerpo_html, nombre_residencial, boton_texto=None, boton_url=None):
    """
    Plantilla HTML simple y compatible con la mayoría de clientes de
    correo (sin CSS externo ni JS -- Gmail/Outlook/etc. los descartan).
    Usa el naranja/azul de marca de SICA-VS como base; no usa el color
    dinámico de cada residencial acá a propósito -- a diferencia de los
    PDFs (que se abren DESPUÉS de haber iniciado sesión, con la
    residencial ya identificada), este correo es lo PRIMERO que ve un
    residente, antes incluso de tener sesión -- más simple y confiable
    usar la marca fija de la plataforma.
    """
    boton_html = ""
    if boton_texto and boton_url:
        boton_html = f"""
        <tr><td style="padding: 24px 0;">
          <a href="{boton_url}" style="background:#F48723;color:#ffffff;text-decoration:none;
             padding:14px 32px;border-radius:10px;font-weight:600;font-size:15px;
             display:inline-block;">{boton_texto}</a>
        </td></tr>"""
    return f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f7fb;padding:32px 0;">
      <tr><td align="center">
        <table role="presentation" width="480" cellpadding="0" cellspacing="0"
               style="background:#ffffff;border-radius:16px;overflow:hidden;font-family:Arial,sans-serif;">
          <tr><td style="background:#022E45;padding:24px 32px;">
            <span style="color:#ffffff;font-size:20px;font-weight:700;">SICA-VS</span><br/>
            <span style="color:#F5C518;font-size:13px;">{nombre_residencial}</span>
          </td></tr>
          <tr><td style="padding:32px;">
            <h2 style="color:#022E45;margin:0 0 16px;font-size:19px;">{titulo}</h2>
            <div style="color:#3a4048;font-size:14.5px;line-height:1.6;">{cuerpo_html}</div>
            {boton_html}
            <p style="color:#93a0ad;font-size:12px;margin-top:24px;">
              Si el botón no funciona, copiá y pegá este enlace en tu navegador:<br/>
              <span style="word-break:break-all;">{boton_url or ''}</span>
            </p>
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


def enviar_correo_activacion(email, nombre, token, nombre_residencial, es_reenvio=False):
    """Correo con el link para que un residente defina su contraseña."""
    from flask import current_app
    url_frontend = current_app.config.get("FRONTEND_URL", "https://patronatovillasdelsol.com")
    url = f"{url_frontend}/?activar={token}"

    # Día 62 — reescrito a pedido del usuario: el texto anterior era
    # genérico ("Ya tenés una cuenta en SICA-VS"), sin mencionar el nombre
    # de la residencial ni personalizar con el nombre del residente. Ahora
    # el correo es explícitamente multi-residencial: usa el nombre real de
    # la persona y el nombre real de SU residencial (ambos ya llegaban como
    # parámetro, solo faltaba usarlos en el texto).
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
    return _enviar(email, f"Activá tu cuenta — {nombre_residencial}", html)


def enviar_correo_reset(email, token, nombre_residencial):
    """Correo con el link para restablecer una contraseña olvidada."""
    from flask import current_app
    url_frontend = current_app.config.get("FRONTEND_URL", "https://patronatovillasdelsol.com")
    url = f"{url_frontend}/?reset={token}"
    cuerpo = """
      <p>Pediste restablecer tu contraseña en SICA-VS.</p>
      <p>Hacé clic en el botón de abajo para elegir una nueva. Si vos no pediste esto,
      podés ignorar este correo con tranquilidad -- tu contraseña actual sigue funcionando.</p>
      <p style="color:#93a0ad;font-size:13px;">Este enlace vence en 2 horas.</p>"""
    html = _plantilla_base("Restablecer contraseña", cuerpo, nombre_residencial,
                           "Restablecer contraseña", url)
    return _enviar(email, "Restablecer tu contraseña — SICA-VS", html)
