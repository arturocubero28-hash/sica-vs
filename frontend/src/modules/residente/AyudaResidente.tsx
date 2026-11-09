import { useEffect, useState } from "react";
import { Phone, Mail, Copy, Check, MessageCircleQuestion } from "lucide-react";
import { getMiResidencial, miCuenta, type ResidencialDTO } from "../../api/client";
import { copiarTexto } from "../../utils/copiar";

/* Día 76 — sección «Ayuda» del residente: el teléfono y el correo que la
   administración configuró para dudas, quejas y sugerencias. La misma
   sección existe en la app (lib/modules/residente/ayuda_screen.dart). */

export function AyudaResidente() {
  const [res, setRes] = useState<ResidencialDTO | null>(null);
  const [casa, setCasa] = useState("");
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    Promise.all([
      getMiResidencial().catch(() => null),
      miCuenta().catch(() => null),
    ]).then(([r, c]) => {
      setRes(r);
      setCasa(c?.cuenta.nombre_completo || c?.cuenta.identificador || "");
      setCargando(false);
    });
  }, []);

  if (cargando) return <p className="muted">Cargando…</p>;

  const tel = res?.telefono_ayuda || "";
  const correo = res?.email_ayuda || "";
  const asunto = `Consulta${casa ? ` — ${casa}` : ""}`;

  return (
    <div className="ay">
      <header className="ay-cabeza">
        <span className="ay-icono" aria-hidden="true"><MessageCircleQuestion size={26} /></span>
        <div>
          <h2>¿Tenés una duda, una queja o una sugerencia?</h2>
          <p>La administración de {res?.nombre || "la residencial"} quiere escucharte. Llamanos o escribinos
            sobre tu cuenta, tus cuotas, un acceso que no funcionó o cualquier idea para mejorar la residencial.
            Contanos con calma qué pasó: así te podemos ayudar más rápido.</p>
        </div>
      </header>

      {!tel && !correo ? (
        <div className="ay-sin-contacto">
          <p><b>La administración todavía no publicó un teléfono ni un correo.</b></p>
          <p>Mientras tanto, acercate a la oficina de la administración.</p>
        </div>
      ) : (
        <div className="ay-canales">
          {tel && (
            <Canal icono={<Phone size={22} />} titulo="Llamar" valor={tel}
              enlace={`tel:${tel.replace(/[^\d+]/g, "")}`} accion="Llamar ahora"
              nota="Servicio al cliente" />
          )}
          {correo && (
            <Canal icono={<Mail size={22} />} titulo="Escribir un correo" valor={correo}
              enlace={`mailto:${correo}?subject=${encodeURIComponent(asunto)}`} accion="Escribir correo"
              nota="Te respondemos por el mismo medio" />
          )}
        </div>
      )}

      <p className="ay-pie">Si es una emergencia dentro de la residencial, avisale al guardia de la caseta.</p>
    </div>
  );
}

function Canal({ icono, titulo, valor, enlace, accion, nota }: {
  icono: React.ReactNode; titulo: string; valor: string; enlace: string; accion: string; nota: string;
}) {
  const [copiado, setCopiado] = useState(false);
  async function copiar() {
    if (await copiarTexto(valor)) {
      setCopiado(true);
      window.setTimeout(() => setCopiado(false), 2200);
    }
  }
  return (
    <div className="ay-canal">
      <div className="ay-canal-top">
        <span className="ay-canal-icono" aria-hidden="true">{icono}</span>
        <div>
          <span className="ay-canal-titulo">{titulo}</span>
          <span className="ay-canal-nota">{nota}</span>
        </div>
      </div>
      <span className="ay-canal-valor">{valor}</span>
      <div className="ay-canal-acciones">
        <a className="ay-btn" href={enlace}>{accion}</a>
        <button type="button" className={`ay-btn-copiar ${copiado ? "hecho" : ""}`} onClick={copiar}
          aria-label={`Copiar ${valor}`}>
          {copiado ? <><Check size={15} /> Copiado</> : <><Copy size={15} /> Copiar</>}
        </button>
      </div>
    </div>
  );
}
