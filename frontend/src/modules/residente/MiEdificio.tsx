import { useState, useEffect } from "react";
import {
  misEdificios, generarCodigoEnrolamiento, misCodigosEnrolamiento, borrarCodigoEnrolamiento,
  type Unidad, type CodigoEnrolamiento,
} from "../../api/client";

export function MiEdificio() {
  const [edificios, setEdificios] = useState<Unidad[]>([]);
  const [codigos, setCodigos] = useState<CodigoEnrolamiento[]>([]);
  const [cargando, setCargando] = useState(true);
  const [edificioSel, setEdificioSel] = useState("");
  const [apartamento, setApartamento] = useState("");
  const [nota, setNota] = useState("");
  const [generando, setGenerando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "ok" | "err"; texto: string } | null>(null);

  async function cargar() {
    setCargando(true);
    try {
      const [eds, cods] = await Promise.all([misEdificios(), misCodigosEnrolamiento()]);
      setEdificios(eds);
      setCodigos(cods);
      if (eds.length === 1) setEdificioSel(eds[0].id);
    } catch { /* noop */ }
    finally { setCargando(false); }
  }
  useEffect(() => { cargar(); }, []);

  async function generar() {
    if (!edificioSel) { setMsg({ tipo: "err", texto: "Elegí el edificio" }); return; }
    setGenerando(true); setMsg(null);
    try {
      await generarCodigoEnrolamiento({
        edificio_id: edificioSel,
        apartamento: apartamento.trim() || undefined,
        nota: nota.trim() || undefined,
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
    const msg = `Hola, para enrolarte como inquilino en ${c.edificio} de Residencial Villas del Sol, ` +
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
        <p className="muted">Generá códigos para que tus inquilinos se enrolen en la administración</p>
      </div>

      {/* Generar nuevo código */}
      <div className="dash-card">
        <h3>Generar código para un inquilino</h3>
        <p className="muted small">
          El inquilino lleva este código a la oficina de administración, que lo da de alta bajo tu edificio.
          Cada código sirve para un solo inquilino.
        </p>
        {edificios.length > 1 && (
          <div className="form-field">
            <label>Edificio</label>
            <select value={edificioSel} onChange={e => setEdificioSel(e.target.value)}>
              <option value="">— Elegí el edificio —</option>
              {edificios.map(e => <option key={e.id} value={e.id}>{e.identificador}</option>)}
            </select>
          </div>
        )}
        <div className="row">
          <div className="form-field" style={{ flex: 1 }}>
            <label>Apartamento (opcional)</label>
            <input placeholder="Ej. 3B" value={apartamento} onChange={e => setApartamento(e.target.value)} />
          </div>
          <div className="form-field" style={{ flex: 2 }}>
            <label>Nota (opcional)</label>
            <input placeholder="Ej. Familia López, inquilino nuevo" value={nota} onChange={e => setNota(e.target.value)} />
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

      {/* Códigos ya usados */}
      {usados.length > 0 && (
        <div className="dash-card">
          <h3>Inquilinos ya enrolados ({usados.length})</h3>
          <div className="scroll-x">
            <table className="data">
              <thead><tr><th>Código</th><th>Apartamento</th><th>Nota</th><th>Enrolado</th></tr></thead>
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
