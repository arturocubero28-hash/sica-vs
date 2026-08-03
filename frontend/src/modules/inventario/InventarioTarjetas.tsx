import { useState, useEffect } from "react";
import {
  listarTiposTarjeta, crearTipoTarjeta, editarTipoTarjeta, agregarStock,
  type TipoTarjetaDTO,
} from "../../api/client";
import { L } from "../../utils/formato";
import { FuncionNoIncluida } from "../../components/FuncionNoIncluida";
import { Car, Footprints } from "lucide-react";

export function InventarioTarjetas() {
  const [tipos, setTipos] = useState<TipoTarjetaDTO[]>([]);
  const [cargando, setCargando] = useState(true);
  const [creando, setCreando] = useState(false);
  const [stockDe, setStockDe] = useState<TipoTarjetaDTO | null>(null);
  const [errorPlan, setErrorPlan] = useState("");

  function recargar() {
    setCargando(true);
    listarTiposTarjeta().then(setTipos)
      .catch((e) => setErrorPlan(e?.message || "")).finally(() => setCargando(false));
  }
  useEffect(() => { recargar(); }, []);

  if (errorPlan) return <FuncionNoIncluida mensaje={errorPlan} />;

  const totalStock = tipos.reduce((a, t) => a + t.stock, 0);
  const bajoStock = tipos.filter(t => t.activo && t.stock <= 5).length;

  return (
    <div>
      <div className="lista-head">
        <h2>Inventario de tarjetas</h2>
        <button className="cuota-btn-pagar" style={{ maxWidth: 170 }} onClick={() => setCreando(true)}>
          + Nuevo tipo de tarjeta
        </button>
      </div>

      <div className="rep-resumen-grid">
        <div className="rep-kpi"><span>Tipos configurados</span><b>{tipos.length}</b></div>
        <div className="rep-kpi"><span>Total en bodega</span><b>{totalStock}</b></div>
        <div className={`rep-kpi ${bajoStock ? "rep-kpi-alerta" : ""}`}>
          <span>Bajo stock (≤5)</span><b>{bajoStock}</b>
        </div>
      </div>

      {cargando ? <p className="muted">Cargando…</p> : tipos.length === 0 ? (
        <div className="lista-card">
          <p className="muted">No hay tipos de tarjeta configurados todavía.</p>
          <p className="muted small">Creá un tipo (ej. "Tarjeta vehicular UHF") con su precio y stock
            para poder venderlas en caja.</p>
        </div>
      ) : (
        <div className="lista-card"><div className="scroll-x">
          <table className="data">
            <thead><tr><th>Tipo</th><th>Acceso</th><th>Precio</th><th>Stock</th><th>Estado</th><th></th></tr></thead>
            <tbody>
              {tipos.map(t => (
                <tr key={t.id} className={!t.activo ? "fila-baja" : ""}>
                  <td>{t.nombre}</td>
                  <td>
                    <span className={`pill ${t.tipo_acceso === "peatonal" ? "" : "green"}`}>
                      {t.tipo_acceso === "peatonal" ? "<Footprints size={16} /> Corto alcance" : "<Car size={16} /> Largo alcance"}
                    </span>
                  </td>
                  <td>{L(t.precio)}</td>
                  <td>
                    <span className={`pill ${t.stock === 0 ? "red" : t.stock <= 5 ? "amber" : "green"}`}>
                      {t.stock} u.
                    </span>
                  </td>
                  <td>{t.activo ? <span className="pill green">Activo</span> : <span className="pill">Inactivo</span>}</td>
                  <td style={{ display: "flex", gap: 6 }}>
                    <button className="mini" onClick={() => setStockDe(t)}>+ Stock</button>
                    <button className={`mini ${t.activo ? "btn-baja" : "btn-reactivar"}`}
                      onClick={async () => { await editarTipoTarjeta(t.id, { activo: !t.activo }); recargar(); }}>
                      {t.activo ? "Desactivar" : "Activar"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div></div>
      )}

      {creando && <ModalNuevoTipo onCerrar={() => setCreando(false)}
        onCreado={() => { setCreando(false); recargar(); }} />}
      {stockDe && <ModalStock tipo={stockDe} onCerrar={() => setStockDe(null)}
        onHecho={() => { setStockDe(null); recargar(); }} />}
    </div>
  );
}

function ModalNuevoTipo({ onCerrar, onCreado }: { onCerrar: () => void; onCreado: () => void }) {
  const [nombre, setNombre] = useState("");
  const [tipoAcceso, setTipoAcceso] = useState("vehicular");
  const [precio, setPrecio] = useState("");
  const [stock, setStock] = useState("");
  const [error, setError] = useState("");
  const [guardando, setGuardando] = useState(false);

  async function crear() {
    if (!nombre.trim()) { setError("El nombre es obligatorio"); return; }
    setError(""); setGuardando(true);
    try {
      await crearTipoTarjeta({
        nombre, tipo_acceso: tipoAcceso,
        precio: parseFloat(precio) || 0, stock: parseInt(stock) || 0,
      });
      onCreado();
    } catch (e) { setError((e as Error).message); }
    finally { setGuardando(false); }
  }

  return (
    <div className="modal" onClick={onCerrar}>
      <div className="modal-body" onClick={e => e.stopPropagation()}>
        <div className="modal-head"><h3>Nuevo tipo de tarjeta</h3>
          <button className="ghost mini" onClick={onCerrar}>✕</button></div>
        <div className="form-pago">
          <div className="form-field"><label>Nombre</label>
            <input value={nombre} onChange={e => setNombre(e.target.value)} placeholder="Ej. Tarjeta vehicular UHF" /></div>
          <div className="form-field"><label>Tipo de acceso</label>
            <select value={tipoAcceso} onChange={e => setTipoAcceso(e.target.value)}>
              <option value="vehicular"><Car size={16} /> Largo alcance (vehicular)</option>
              <option value="peatonal"><Footprints size={16} /> Corto alcance (peatonal)</option>
            </select></div>
          <div className="form-field"><label>Precio de venta (L)</label>
            <input type="number" value={precio} onChange={e => setPrecio(e.target.value)} placeholder="0.00" /></div>
          <div className="form-field"><label>Stock inicial (unidades)</label>
            <input type="number" value={stock} onChange={e => setStock(e.target.value)} placeholder="0" /></div>
          {error && <div className="error">{error}</div>}
          <button className="cuota-btn-pagar full" onClick={crear} disabled={guardando}>
            {guardando ? "Creando…" : "Crear tipo"}
          </button>
        </div>
      </div>
    </div>
  );
}

function ModalStock({ tipo, onCerrar, onHecho }: {
  tipo: TipoTarjetaDTO; onCerrar: () => void; onHecho: () => void;
}) {
  const [cantidad, setCantidad] = useState("");
  const [nota, setNota] = useState("");
  const [error, setError] = useState("");
  const [guardando, setGuardando] = useState(false);

  async function registrar() {
    const c = parseInt(cantidad);
    if (!c) { setError("Ingresá una cantidad distinta de cero"); return; }
    setError(""); setGuardando(true);
    try {
      await agregarStock(tipo.id, c, nota);
      onHecho();
    } catch (e) { setError((e as Error).message); }
    finally { setGuardando(false); }
  }

  return (
    <div className="modal" onClick={onCerrar}>
      <div className="modal-body" onClick={e => e.stopPropagation()}>
        <div className="modal-head"><h3>Entrada de stock</h3>
          <button className="ghost mini" onClick={onCerrar}>✕</button></div>
        <p className="muted">{tipo.nombre} · stock actual: <b>{tipo.stock}</b> unidades</p>
        <div className="form-pago">
          <div className="form-field"><label>Cantidad a agregar</label>
            <input type="number" value={cantidad} onChange={e => setCantidad(e.target.value)}
              placeholder="Ej. 50 (compra de lote)" /></div>
          <p className="muted small">Usá un número negativo para corregir el stock por una baja de bodega.</p>
          <div className="form-field"><label>Nota (opcional)</label>
            <input value={nota} onChange={e => setNota(e.target.value)} placeholder="Ej. Compra a proveedor X" /></div>
          {error && <div className="error">{error}</div>}
          <button className="cuota-btn-pagar full" onClick={registrar} disabled={guardando}>
            {guardando ? "Registrando…" : "Registrar entrada"}
          </button>
        </div>
      </div>
    </div>
  );
}
