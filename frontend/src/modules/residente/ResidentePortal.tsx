import { useState, useEffect } from "react";
import {
  miCuenta, misVisitas, crearVisita, cancelarVisita, urlImagenQR, obtenerImagenQR,
  type MiCuentaDTO, type VisitaDTO,
} from "../../api/client";
import { CuotasResidente } from "./CuotasResidente";
import { HomeResidente } from "./HomeResidente";
import { MiEdificio } from "./MiEdificio";

// Comparte el QR por WhatsApp (descarga la imagen y abre WhatsApp con mensaje)
async function compartirWhatsApp(visita: VisitaDTO) {
  const vigencia = visita.valido_hasta
    ? new Date(visita.valido_hasta).toLocaleString()
    : "";
  const mensaje =
    `Hola ${visita.nombre_visitante}, aquí está tu código de acceso para Residencial Villas del Sol. ` +
    `Preséntalo al guardia en la entrada.` +
    (vigencia ? ` Válido hasta: ${vigencia}.` : "");

  // Intentar compartir la imagen nativamente (móvil)
  try {
    const blob = await obtenerImagenQR(visita.id);
    const file = new File([blob], "qr-visita.png", { type: "image/png" });
    if (navigator.canShare && navigator.canShare({ files: [file] })) {
      await navigator.share({ files: [file], text: mensaje });
      return;
    }
  } catch { /* sigue al fallback */ }

  // Fallback: abrir WhatsApp con el mensaje de texto
  window.open(`https://wa.me/?text=${encodeURIComponent(mensaje)}`, "_blank");
}

// Comparte el código numérico de delivery por WhatsApp (texto, sin imagen)
async function compartirCodigoWhatsApp(visita: VisitaDTO) {
  const vigencia = visita.valido_hasta
    ? new Date(visita.valido_hasta).toLocaleString()
    : "";
  const mensaje =
    `Hola ${visita.nombre_visitante}, tu código de acceso para Residencial Villas del Sol es: ` +
    `*${visita.codigo_numerico}*. Dáselo al guardia en la entrada.` +
    (vigencia ? ` Válido hasta: ${vigencia}.` : "");
  window.open(`https://wa.me/?text=${encodeURIComponent(mensaje)}`, "_blank");
}

// Descarga la imagen del QR
async function descargarQR(visita: VisitaDTO) {
  try {
    const blob = await obtenerImagenQR(visita.id);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `qr_${visita.nombre_visitante.replace(/ /g, "_")}.png`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    alert("No se pudo descargar la imagen");
  }
}

export function ResidentePortal({ seccion = "home" }: { seccion?: string }) {
  const [cuenta, setCuenta] = useState<MiCuentaDTO | null>(null);

  useEffect(() => {
    function cargar() { miCuenta().then(setCuenta).catch(() => {}); }
    cargar();
    // Si el admin aprueba un pago mientras el portal está abierto, al volver
    // el foco a la ventana se recarga el estado (el banner de mora se actualiza
    // sin tener que recargar la página).
    window.addEventListener("focus", cargar);
    return () => window.removeEventListener("focus", cargar);
  }, []);

  return (
    <div className="card wide">
      {cuenta?.cuenta.bloqueada && (
        <div className="error">Tu cuenta está bloqueada por mora. No puedes generar códigos QR hasta regularizar tu pago.</div>
      )}

      {seccion === "home" && <HomeResidente />}
      {seccion === "qr" && <GenerarQR bloqueada={cuenta?.cuenta.bloqueada || false} />}
      {seccion === "historial" && <Historial />}
      {seccion === "cuotas" && <CuotasResidente />}
      {seccion === "edificio" && <MiEdificio />}
      {seccion === "cuenta" && cuenta && <EstadoCuenta data={cuenta} />}
    </div>
  );
}

// ─── 3 Cards de QR ───────────────────────────────────────────
function GenerarQR({ bloqueada }: { bloqueada: boolean }) {
  const [tipo, setTipo] = useState<string | null>(null);

  if (bloqueada) return <p className="muted">Funcionalidad deshabilitada por mora.</p>;

  if (!tipo) {
    return (
      <div className="qr-cards">
        <div className="qr-card" onClick={() => setTipo("unica")}>
          <div className="qr-icon">👤</div>
          <h3>Visita única</h3>
          <p>Una sola entrada. Ideal para visitas puntuales.</p>
        </div>
        <div className="qr-card" onClick={() => setTipo("recurrente")}>
          <div className="qr-icon">🔄</div>
          <h3>Visita recurrente</h3>
          <p>Acceso por un periodo. Para empleadas, familiares frecuentes.</p>
        </div>
        <div className="qr-card" onClick={() => setTipo("repartidor")}>
          <div className="qr-icon">📦</div>
          <h3>Repartidor</h3>
          <p>Delivery o servicio de envío. Vigencia de 6 horas.</p>
        </div>
      </div>
    );
  }

  return <FormQR tipo={tipo} onVolver={() => setTipo(null)} />;
}

function FormQR({ tipo, onVolver }: { tipo: string; onVolver: () => void }) {
  const [nombre, setNombre] = useState("");
  const [documento, setDocumento] = useState("");
  const [telefono, setTelefono] = useState("");
  const [empresa, setEmpresa] = useState("");
  const [placa, setPlaca] = useState("");
  const [enVehiculo, setEnVehiculo] = useState(false);
  const [validoHasta, setValidoHasta] = useState("");
  const [modo, setModo] = useState("libre");
  const [resultado, setResultado] = useState<VisitaDTO | null>(null);
  const [error, setError] = useState("");

  const titulos: Record<string, string> = {
    unica: "Visita única",
    recurrente: "Visita recurrente",
    repartidor: "Repartidor / Delivery",
  };

  async function generar() {
    setError("");
    if (!nombre.trim()) { setError("El nombre es obligatorio"); return; }
    if (tipo === "recurrente" && !validoHasta) { setError("Indica hasta cuándo es válido"); return; }
    try {
      const v = await crearVisita({
        tipo, nombre_visitante: nombre, documento_id: documento || undefined,
        telefono: telefono || undefined, empresa: tipo === "repartidor" ? empresa : undefined,
        placa_vehiculo: placa || undefined, en_vehiculo: enVehiculo,
        valido_hasta: tipo === "recurrente" ? new Date(validoHasta).toISOString() : undefined,
        modo_recurrencia: tipo === "recurrente" ? modo : undefined,
      });
      setResultado(v);
    } catch (e) { setError((e as Error).message); }
  }

  if (resultado) {
    const esDelivery = resultado.tipo === "repartidor" && resultado.codigo_numerico;
    return (
      <div className="qr-resultado">
        <h3>¡{esDelivery ? "Código generado" : "QR generado"}!</h3>

        {esDelivery ? (
          <>
            <div className="codigo-delivery">
              <span className="codigo-delivery-label">Código de acceso</span>
              <span className="codigo-delivery-numero">{resultado.codigo_numerico}</span>
              <span className="muted small">Válido por 6 horas</span>
            </div>
            <p>Dale este código a <b>{resultado.nombre_visitante}</b>. El guardia lo ingresará manualmente en la caseta. No necesita escanear nada.</p>
            <div className="row-btns">
              <button onClick={() => compartirCodigoWhatsApp(resultado)}>
                Compartir por WhatsApp
              </button>
            </div>
          </>
        ) : (
          <>
            <img
              className="qr-imagen"
              src={urlImagenQR(resultado.id)}
              alt="Código QR de la visita"
            />
            <p>Compartí esta imagen con <b>{resultado.nombre_visitante}</b> para que la presente al guardia.</p>
            <div className="row-btns">
              <button onClick={() => compartirWhatsApp(resultado)}>
                Compartir por WhatsApp
              </button>
              <button onClick={() => descargarQR(resultado)}>
                Descargar imagen
              </button>
            </div>
          </>
        )}

        <button className="ghost" style={{ marginTop: 10 }} onClick={onVolver}>
          Generar otro
        </button>
      </div>
    );
  }

  return (
    <div className="form">
      <div className="form-head">
        <button className="ghost mini" onClick={onVolver}>← Volver</button>
        <h3>{titulos[tipo]}</h3>
      </div>

      <input placeholder="Nombre del visitante *" value={nombre} onChange={e => setNombre(e.target.value)} />
      <input placeholder="Número de identidad" value={documento} onChange={e => setDocumento(e.target.value)} />
      <input placeholder="Teléfono" value={telefono} onChange={e => setTelefono(e.target.value)} />

      {tipo === "repartidor" && (
        <input placeholder="Empresa (PedidosYa, Uber Eats...)" value={empresa} onChange={e => setEmpresa(e.target.value)} />
      )}

      <label className="check-label">
        <input type="checkbox" checked={enVehiculo} onChange={e => setEnVehiculo(e.target.checked)} />
        Viene en vehículo
      </label>
      {enVehiculo && <input placeholder="Placa del vehículo" value={placa} onChange={e => setPlaca(e.target.value)} />}

      {tipo === "recurrente" && (
        <>
          <div className="sub">Válido hasta</div>
          <input type="date" value={validoHasta} onChange={e => setValidoHasta(e.target.value)} />
          <div className="sub">Modo de acceso</div>
          <select value={modo} onChange={e => setModo(e.target.value)}>
            <option value="libre">Entrada y salida libre</option>
            <option value="una_por_dia">Una entrada y salida por día</option>
          </select>
        </>
      )}

      {error && <div className="error">{error}</div>}
      <button onClick={generar}>Generar código QR</button>
    </div>
  );
}

// ─── Mis Visitas (Activas / Histórico) ───────────────────────
function Historial() {
  const [visitas, setVisitas] = useState<VisitaDTO[]>([]);
  const [cancelando, setCancelando] = useState<string | null>(null);
  const [tab, setTab] = useState<"activas" | "historico">("activas");
  const [verCodigo, setVerCodigo] = useState<VisitaDTO | null>(null);

  function recargar() { misVisitas().then(setVisitas).catch(() => {}); }
  useEffect(() => {
    recargar();
    // Recargar cuando el residente vuelve a la pestaña (ve cambios de estado al instante)
    const onFocus = () => recargar();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, []);

  async function cancelar(v: VisitaDTO) {
    if (!confirm(`¿Cancelar la visita de ${v.nombre_visitante}? El código dejará de funcionar.`)) return;
    setCancelando(v.id);
    try {
      const actualizada = await cancelarVisita(v.id);
      setVisitas(prev => prev.map(x => x.id === v.id ? actualizada : x));
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setCancelando(null);
    }
  }

  const tipos: Record<string, string> = { unica: "Única", recurrente: "Recurrente", repartidor: "Delivery" };
  // El estado mostrado prioriza el estado real (adentro/salió por eventos)
  function estadoMostrado(v: VisitaDTO): { label: string; color: string } {
    const real = v.estado_real;
    if (real === "adentro") return { label: "Adentro", color: "green" };
    if (real === "salio") return { label: "Salió", color: "amber" };
    // sin eventos aún: usar el estado base
    const map: Record<string, { label: string; color: string }> = {
      activa: { label: "Activa", color: "green" },
      usada: { label: "Ingresó", color: "amber" },
      expirada: { label: "Expirada", color: "" },
      revocada: { label: "Cancelada", color: "red" },
    };
    return map[v.estado] || { label: v.estado, color: "" };
  }

  // Activas = aún no ha salido y el código sigue vigente
  // Histórico = ya salió, expiró o se canceló
  function esActiva(v: VisitaDTO): boolean {
    if (v.estado_real === "adentro") return true;       // está dentro ahora
    if (v.estado_real === "salio") return false;        // ya salió → histórico
    return v.estado === "activa";                        // sin eventos: estado base
  }
  const activas = visitas.filter(esActiva);
  const historico = visitas.filter(v => !esActiva(v));
  const lista = tab === "activas" ? activas : historico;

  function tarjeta(v: VisitaDTO) {
    const esDelivery = v.tipo === "repartidor" && v.codigo_numerico;
    return (
      <div key={v.id} className="visita-item">
        <div className="visita-item-top">
          <div className="visita-nombre">
            {v.nombre_visitante}
            {v.empresa ? <span className="muted small"> · {v.empresa}</span> : ""}
          </div>
          <span className={`pill ${estadoMostrado(v).color}`}>
            {estadoMostrado(v).label}
          </span>
        </div>
        <div className="visita-meta">
          <span className="visita-tag">{tipos[v.tipo] || v.tipo}</span>
          {v.documento_id && <span className="muted small">ID: {v.documento_id}</span>}
          {v.en_vehiculo && v.placa_vehiculo && <span className="muted small">🚗 {v.placa_vehiculo}</span>}
        </div>
        <div className="visita-fecha muted small">
          {v.created_at ? new Date(v.created_at).toLocaleString() : "—"}
        </div>
        {esActiva(v) && (
          <div className="visita-acciones">
            <button className="mini" onClick={() => setVerCodigo(v)}>
              {esDelivery ? "Ver / compartir código" : "Ver / compartir QR"}
            </button>
            {v.estado === "activa" && v.estado_real !== "adentro" && v.estado_real !== "salio" && (
              <button
                className="ghost mini visita-cancelar"
                onClick={() => cancelar(v)}
                disabled={cancelando === v.id}
              >
                {cancelando === v.id ? "Cancelando…" : "Cancelar"}
              </button>
            )}
          </div>
        )}
      </div>
    );
  }

  return (
    <div>
      <div className="hist-tabs">
        <button className={`hist-tab ${tab === "activas" ? "on" : ""}`} onClick={() => setTab("activas")}>
          Activas ({activas.length})
        </button>
        <button className={`hist-tab ${tab === "historico" ? "on" : ""}`} onClick={() => setTab("historico")}>
          Histórico ({historico.length})
        </button>
      </div>

      {lista.length === 0 ? (
        <p className="muted" style={{ marginTop: 16 }}>
          {tab === "activas" ? "No tenés visitas activas en este momento." : "No hay visitas en el histórico."}
        </p>
      ) : (
        <div className="visita-list">{lista.map(tarjeta)}</div>
      )}

      {verCodigo && (
        <ModalCompartirCodigo visita={verCodigo} onCerrar={() => setVerCodigo(null)} />
      )}
    </div>
  );
}

// ─── Modal para volver a ver/compartir un código ya generado ──
function ModalCompartirCodigo({ visita, onCerrar }: { visita: VisitaDTO; onCerrar: () => void }) {
  const esDelivery = visita.tipo === "repartidor" && visita.codigo_numerico;
  return (
    <div className="modal" onClick={onCerrar}>
      <div className="modal-body" onClick={e => e.stopPropagation()} style={{ maxWidth: 420 }}>
        <div className="modal-head">
          <h3>{esDelivery ? "Código de acceso" : "Código QR"}</h3>
          <button className="ghost mini" onClick={onCerrar}>✕</button>
        </div>
        {esDelivery ? (
          <>
            <div className="codigo-delivery">
              <span className="codigo-delivery-label">Código de acceso</span>
              <span className="codigo-delivery-numero">{visita.codigo_numerico}</span>
            </div>
            <p className="muted small">Dale este código a {visita.nombre_visitante}. El guardia lo ingresa manualmente.</p>
            <button className="cuota-btn-pagar full" onClick={() => compartirCodigoWhatsApp(visita)}>
              Compartir por WhatsApp
            </button>
          </>
        ) : (
          <>
            <img className="qr-imagen" src={urlImagenQR(visita.id)} alt="Código QR" />
            <p className="muted small">Compartí esta imagen con {visita.nombre_visitante}.</p>
            <div className="row-btns">
              <button onClick={() => compartirWhatsApp(visita)}>Compartir por WhatsApp</button>
              <button className="ghost" onClick={() => descargarQR(visita)}>Descargar</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ─── Estado de cuenta ────────────────────────────────────────
function EstadoCuenta({ data }: { data: MiCuentaDTO }) {
  const { cuenta, residente } = data;
  return (
    <div className="estado-cuenta">
      <div className="estado-grid">
        <div className="estado-item">
          <span className="muted small">Estado</span>
          <span className={`pill big ${cuenta.bloqueada ? "red" : "green"}`}>
            {cuenta.bloqueada ? "Bloqueada por mora" : cuenta.estado === "al_dia" ? "Al día" : cuenta.estado}
          </span>
        </div>
        <div className="estado-item">
          <span className="muted small">Tarifa</span>
          <b>{cuenta.tarifa} — L {cuenta.monto}</b>
        </div>
        <div className="estado-item">
          <span className="muted small">Día de pago</span>
          <b>Día {cuenta.dia_pago} de cada mes</b>
        </div>
        <div className="estado-item">
          <span className="muted small">Tu rol</span>
          <b>{residente.rol_cuenta === "titular" ? "Titular (encargado)" : "Miembro"}</b>
        </div>
      </div>

      {residente.rol_cuenta === "titular" && (
        <div className="nota" style={{ marginTop: 16 }}>
          <b>Pagar cuota:</b> Realiza una transferencia y sube tu comprobante.
          La administración lo revisará y aprobará tu pago.
        </div>
      )}

      <button className="ghost" style={{ marginTop: 12 }} disabled>
        Pagar con pasarela — Disponible más adelante
      </button>
    </div>
  );
}
