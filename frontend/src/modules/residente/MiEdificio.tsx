import { useState, useEffect } from "react";
import {
  misEdificios, apartamentosDelEdificio, generarCodigoEnrolamiento,
  misCodigosEnrolamiento, borrarCodigoEnrolamiento, crearSolicitudBaja,
  type Unidad, type Cuenta, type CodigoEnrolamiento,
} from "../../api/client";
import { useMiResidencial } from "../../hooks/useMiResidencial";

export function MiEdificio() {
  const { nombre: nombreResidencial } = useMiResidencial();
  const [edificios, setEdificios] = useState<Unidad[]>([]);
  const [codigos, setCodigos] = useState<CodigoEnrolamiento[]>([]);
  const [apartamentos, setApartamentos] = useState<Cuenta[]>([]);
  const [cargando, setCargando] = useState(true);
  const [edificioSel, setEdificioSel] = useState("");
  const [apartamento, setApartamento] = useState("");
  const [nota, setNota] = useState("");
  const [generando, setGenerando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "ok" | "err"; texto: string } | null>(null);
  const [aptoDetalle, setAptoDetalle] = useState<Cuenta | null>(null);

  async function cargar() {
    setCargando(true);
    try {
      const [eds, cods] = await Promise.all([misEdificios(), misCodigosEnrolamiento()]);
      setEdificios(eds);
      setCodigos(cods);
      const selId = edificioSel || (eds.length === 1 ? eds[0].id : "");
      if (selId) {
        setEdificioSel(selId);
        try {
          const aptos = await apartamentosDelEdificio(selId);
          setApartamentos(aptos);
        } catch { setApartamentos([]); }
      }
    } catch { /* noop */ }
    finally { setCargando(false); }
  }
  useEffect(() => { cargar(); }, []);

  async function cambiarEdificio(id: string) {
    setEdificioSel(id);
    if (id) {
      try {
        const aptos = await apartamentosDelEdificio(id);
        setApartamentos(aptos);
      } catch { setApartamentos([]); }
    }
  }

  async function generar() {
    if (!edificioSel) { setMsg({ tipo: "err", texto: "Elegí el edificio" }); return; }
    if (!apartamento.trim()) { setMsg({ tipo: "err", texto: "El número de apartamento es obligatorio" }); return; }
    if (!nota.trim()) { setMsg({ tipo: "err", texto: "El nombre del inquilino es obligatorio" }); return; }
    setGenerando(true); setMsg(null);
    try {
      await generarCodigoEnrolamiento({
        edificio_id: edificioSel,
        apartamento: apartamento.trim(),
        nota: nota.trim(),
      });
      setApartamento(""); setNota("");
      setMsg({ tipo: "ok", texto: "Código generado. Compartilo con tu inquilino." });
      cargar();
      setTimeout(() => setMsg(null), 4000);
    } catch (e) { setMsg({ tipo: "err", texto: (e as Error).message }); }
    finally { setGenerando(false); }
  }

  async function borrar(id: string) {
    if (!confirm("¿Borrar este código? No podrá usarse después.")) return;
    try { await borrarCodigoEnrolamiento(id); cargar(); }
    catch (e) { setMsg({ tipo: "err", texto: (e as Error).message }); }
  }

  function compartir(c: CodigoEnrolamiento) {
    const msg = `Hola, para enrolarte como inquilino en ${c.edificio} de Residencial ${nombreResidencial}, ` +
      `andá a la oficina de administración y dictá este código: ${c.codigo}` +
      (c.apartamento_sugerido ? ` (Apartamento ${c.apartamento_sugerido})` : "");
    window.open(`https://wa.me/?text=${encodeURIComponent(msg)}`, "_blank");
  }

  if (cargando) return <p className="muted">Cargando…</p>;

  const activos = codigos.filter(c => c.estado === "activo");
  const usados = codigos.filter(c => c.estado === "usado");

  return (
    <div className="mi-edificio">
      <div className="home-saludo">
        <h2>Mi edificio</h2>
        <p className="muted">Administrá tus inquilinos y generá códigos de enrolamiento</p>
      </div>

      {/* ── Apartamentos del edificio ── */}
      {apartamentos.length > 0 && (
        <div className="dash-card">
          <h3>Apartamentos del edificio ({apartamentos.length})</h3>
          <div className="aptos-lista">
            {apartamentos.map(a => {
              const bloqueada = a.bloqueada;
              const esAdmin = a.tipo_cuenta === "edificio_admin";
              return (
                <div key={a.id} className="apto-card" onClick={() => !esAdmin && setAptoDetalle(a)}>
                  <div className="apto-card-icon" style={{ background: esAdmin ? "rgba(2,46,69,0.1)" : "rgba(244,135,35,0.1)" }}>
                    {esAdmin ? "👑" : "🚪"}
                  </div>
                  <div className="apto-card-info">
                    <b>Apto {a.apartamento || "—"}</b>
                    {esAdmin && <span className="pill-inline">Admin</span>}
                    <span className="muted small">{a.nombre_completo || "—"}</span>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    {a.tarifa && <span className="small">L {(a as any).monto ?? "—"}</span>}
                    <span className={`pill-estado ${bloqueada ? "pill-estado--mora" : "pill-estado--ok"}`}>
                      {bloqueada ? "Con deuda" : "Al día"}
                    </span>
                  </div>
                  {!esAdmin && <span className="apto-card-arrow">›</span>}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Modal detalle de apartamento ── */}
      {aptoDetalle && (
        <ModalDetalleApto
          cuenta={aptoDetalle}
          onCerrar={() => setAptoDetalle(null)}
          onSolicitada={() => { setAptoDetalle(null); cargar(); }}
        />
      )}

      {/* ── Generar nuevo código ── */}
      <div className="dash-card">
        <h3>Generar código para un inquilino</h3>
        <p className="muted small">
          El inquilino lleva este código a la oficina de administración, que lo da de alta bajo tu edificio.
          Cada código sirve para un solo inquilino.
        </p>
        {edificios.length > 1 && (
          <div className="form-field">
            <label>Edificio</label>
            <select value={edificioSel} onChange={e => cambiarEdificio(e.target.value)}>
              <option value="">— Elegí el edificio —</option>
              {edificios.map(e => <option key={e.id} value={e.id}>{e.identificador}</option>)}
            </select>
          </div>
        )}
        <div className="row">
          <div className="form-field" style={{ flex: 1 }}>
            <label>Apartamento *</label>
            <input placeholder="Ej. 3B" value={apartamento} onChange={e => setApartamento(e.target.value)} />
          </div>
          <div className="form-field" style={{ flex: 2 }}>
            <label>Nombre del inquilino *</label>
            <input placeholder="Ej. Familia López" value={nota} onChange={e => setNota(e.target.value)} />
          </div>
        </div>
        <button className="cuota-btn-pagar" onClick={generar} disabled={generando}>
          {generando ? "Generando…" : "+ Generar código"}
        </button>
        {msg && <div className={msg.tipo === "ok" ? "cuota-ok" : "error"} style={{ marginTop: 10 }}>{msg.texto}</div>}
      </div>

      {/* Códigos activos */}
      <div className="dash-card">
        <h3>Códigos activos ({activos.length})</h3>
        {activos.length === 0 ? (
          <p className="muted">No tenés códigos activos. Generá uno arriba.</p>
        ) : (
          <div className="codigos-lista">
            {activos.map(c => (
              <div key={c.id} className="codigo-card">
                <div className="codigo-numero">{c.codigo}</div>
                <div className="codigo-info">
                  <b>{c.edificio}</b>
                  {c.apartamento_sugerido ? ` · Apto ${c.apartamento_sugerido}` : ""}
                  {c.nota ? <div className="muted small">{c.nota}</div> : null}
                </div>
                <div className="codigo-acciones">
                  <button className="mini" onClick={() => compartir(c)}>Compartir</button>
                  <button className="ghost mini" style={{ color: "#c81e1e" }} onClick={() => borrar(c.id)}>Borrar</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Historial */}
      {usados.length > 0 && (
        <div className="dash-card">
          <h3>Historial de enrolamiento ({usados.length})</h3>
          <div className="scroll-x">
            <table className="data">
              <thead><tr><th>Código</th><th>Apartamento</th><th>Nombre</th><th>Enrolado</th></tr></thead>
              <tbody>
                {usados.map(c => (
                  <tr key={c.id}>
                    <td><span className="muted">{c.codigo}</span></td>
                    <td>{c.apartamento_sugerido || "—"}</td>
                    <td className="small">{c.nota || "—"}</td>
                    <td className="small">{c.usado_en ? new Date(c.usado_en).toLocaleDateString("es-HN") : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Modal detalle de apartamento + solicitar baja ── */
function ModalDetalleApto({ cuenta, onCerrar, onSolicitada }: {
  cuenta: Cuenta; onCerrar: () => void; onSolicitada: () => void;
}) {
  const [motivo, setMotivo] = useState("");
  const [fechaDes, setFechaDes] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState("");
  const [exito, setExito] = useState(false);

  async function solicitar() {
    if (!motivo.trim()) { setError("El motivo es obligatorio"); return; }
    if (!fechaDes) { setError("Seleccioná la fecha de desocupación"); return; }
    setEnviando(true); setError("");
    try {
      await crearSolicitudBaja({
        cuenta_id: cuenta.id,
        motivo: motivo.trim(),
        fecha_desocupacion: fechaDes,
      });
      setExito(true);
    } catch (e) { setError((e as Error).message); }
    finally { setEnviando(false); }
  }

  const titular = cuenta.titular;
  const bloqueada = cuenta.bloqueada;

  return (
    <div className="modal" onClick={onCerrar}>
      <div className="modal-body" onClick={e => e.stopPropagation()} style={{ maxWidth: 500 }}>
        <div className="modal-head">
          <h3>🚪 Apartamento {cuenta.apartamento || "—"}</h3>
          <button className="ghost mini" onClick={onCerrar}>Cerrar</button>
        </div>

        {exito ? (
          <div style={{ padding: 20, textAlign: "center" }}>
            <div style={{ fontSize: 48 }}>✓</div>
            <h3 style={{ color: "#166534" }}>Solicitud enviada</h3>
            <p className="muted">La administración revisará tu solicitud y procederá con la baja.</p>
            <button onClick={onSolicitada} style={{ marginTop: 14 }}>Cerrar</button>
          </div>
        ) : (
          <div style={{ padding: "0 4px" }}>
            {/* Info del inquilino */}
            <div className="datos-grid" style={{ marginBottom: 16 }}>
              <div className="dato-item">
                <span className="muted small">Titular</span>
                <span><b>{cuenta.nombre_completo || "—"}</b></span>
              </div>
              <div className="dato-item">
                <span className="muted small">Estado</span>
                <span className={bloqueada ? "pill-estado pill-estado--mora" : "pill-estado pill-estado--ok"}>
                  {bloqueada ? "Con deuda" : "Al día"}
                </span>
              </div>
              {titular?.email && (
                <div className="dato-item">
                  <span className="muted small">Correo</span>
                  <span>{titular.email}</span>
                </div>
              )}
              {titular?.telefono && (
                <div className="dato-item">
                  <span className="muted small">Teléfono</span>
                  <span>{titular.telefono}</span>
                </div>
              )}
              {cuenta.tarifa && (
                <div className="dato-item">
                  <span className="muted small">Tarifa</span>
                  <span>{cuenta.tarifa} — L {(cuenta as any).monto ?? "—"}</span>
                </div>
              )}
              {cuenta.created_at && (
                <div className="dato-item">
                  <span className="muted small">Enrolado desde</span>
                  <span>{new Date(cuenta.created_at).toLocaleDateString("es-HN")}</span>
                </div>
              )}
            </div>

            {bloqueada ? (
              <div className="error" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                ⚠ Esta cuenta tiene deuda pendiente. Debe estar al día para solicitar la baja.
              </div>
            ) : (
              <>
                <div className="sub" style={{ marginTop: 8 }}>Solicitar dar de baja</div>
                <p className="muted small" style={{ margin: "4px 0 12px" }}>
                  La administración revisará tu solicitud y procederá con la baja.
                </p>
                <textarea
                  placeholder="Motivo de la baja (ej. terminó contrato, se mudó) *"
                  value={motivo}
                  onChange={e => setMotivo(e.target.value)}
                  rows={3}
                  style={{ width: "100%", resize: "vertical" }}
                />
                <div style={{ marginTop: 10 }}>
                  <label className="muted small">Fecha de desocupación *</label>
                  <input type="date" value={fechaDes} onChange={e => setFechaDes(e.target.value)}
                    max={new Date().toISOString().split("T")[0]} />
                </div>
                {error && <div className="error" style={{ marginTop: 10 }}>⚠ {error}</div>}
                <button onClick={solicitar} disabled={enviando}
                  style={{ marginTop: 14, background: "#dc2626", width: "100%" }}>
                  {enviando ? "Enviando…" : "Solicitar dar de baja"}
                </button>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
