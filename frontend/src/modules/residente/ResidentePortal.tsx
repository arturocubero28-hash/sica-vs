import { useState, useEffect } from "react";
import {
  miCuenta, misVisitas, crearVisita, cancelarVisita, urlImagenQR, obtenerImagenQR,
  type MiCuentaDTO, type VisitaDTO,
} from "../../api/client";

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

export function ResidentePortal({ seccion = "qr" }: { seccion?: string }) {
  const [cuenta, setCuenta] = useState<MiCuentaDTO | null>(null);

  useEffect(() => { miCuenta().then(setCuenta).catch(() => {}); }, []);

  return (
    <div className="card wide">
      {cuenta?.cuenta.bloqueada && (
        <div className="error">Tu cuenta está bloqueada por mora. No puedes generar códigos QR hasta regularizar tu pago.</div>
      )}

      {seccion === "qr" && <GenerarQR bloqueada={cuenta?.cuenta.bloqueada || false} />}
      {seccion === "historial" && <Historial />}
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
    return (
      <div className="qr-resultado">
        <h3>¡QR generado!</h3>
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

// ─── Historial ───────────────────────────────────────────────
function Historial() {
  const [visitas, setVisitas] = useState<VisitaDTO[]>([]);
  const [cancelando, setCancelando] = useState<string | null>(null);

  useEffect(() => { misVisitas().then(setVisitas).catch(() => {}); }, []);

  async function cancelar(v: VisitaDTO) {
    if (!confirm(`¿Cancelar la visita de ${v.nombre_visitante}? El código QR dejará de funcionar.`)) return;
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

  if (visitas.length === 0) return <p className="muted">No tienes visitas registradas.</p>;

  const tipos: Record<string, string> = { unica: "Única", recurrente: "Recurrente", repartidor: "Delivery" };
  const estadoLabel: Record<string, string> = {
    activa: "Activa",
    usada: "Ingresó",
    expirada: "Expirada",
    revocada: "Cancelada",
  };
  const estadoColor: Record<string, string> = {
    activa: "green",
    usada: "amber",
    expirada: "",
    revocada: "red",
  };

  return (
    <div className="visita-list">
      {visitas.map(v => (
        <div key={v.id} className="visita-item">
          <div className="visita-item-top">
            <div className="visita-nombre">
              {v.nombre_visitante}
              {v.empresa ? <span className="muted small"> · {v.empresa}</span> : ""}
            </div>
            <span className={`pill ${estadoColor[v.estado] || ""}`}>
              {estadoLabel[v.estado] || v.estado}
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
          {v.estado === "activa" && (
            <button
              className="ghost mini visita-cancelar"
              onClick={() => cancelar(v)}
              disabled={cancelando === v.id}
            >
              {cancelando === v.id ? "Cancelando…" : "Cancelar visita"}
            </button>
          )}
        </div>
      ))}
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
