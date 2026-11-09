import { useEffect, useState } from "react";
import { Landmark, LifeBuoy, Pencil, Trash2, Plus, Check, X } from "lucide-react";
import {
  getMiResidencial, setMiResidencial, getCuentasBancarias, crearCuentaBancaria,
  editarCuentaBancaria, borrarCuentaBancaria,
  type CuentaBancariaDTO, type TipoCuentaBancaria,
} from "../../api/client";

/* Día 76 — dos tarjetas de la pestaña Configuración del admin:
   - el contacto que los residentes ven en «Ayuda» (app y portal);
   - las cuentas bancarias a las que pueden pagar sus cuotas. */

// Los bancos más comunes en Honduras, como sugerencia (se puede escribir otro).
const BANCOS_HN = [
  "Banco Atlántida", "BAC Credomatic", "Banco Ficohsa", "Banpaís", "Banco de Occidente",
  "Davivienda", "Banrural", "Banco Lafise", "Banco Promerica", "Banco Azteca",
  "Banco de los Trabajadores", "Banco Cuscatlán", "Banco Popular",
];

export const TIPO_CUENTA_TEXTO: Record<TipoCuentaBancaria, string> = {
  ahorro: "Cuenta de ahorro", cheques: "Cuenta de cheques",
};

// ── Contacto de ayuda ──────────────────────────────────────────────────────
export function ContactoAyudaPanel() {
  const [telefono, setTelefono] = useState("");
  const [email, setEmail] = useState("");
  const [guardado, setGuardado] = useState({ telefono: "", email: "" });
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    getMiResidencial().then(r => {
      const t = r?.telefono_ayuda || "", e = r?.email_ayuda || "";
      setTelefono(t); setEmail(e); setGuardado({ telefono: t, email: e });
    }).catch(() => setError("No se pudo cargar el contacto de ayuda"))
      .finally(() => setCargando(false));
  }, []);

  const cambio = telefono.trim() !== guardado.telefono || email.trim().toLowerCase() !== guardado.email;

  async function guardar() {
    setGuardando(true); setMsg(""); setError("");
    try {
      const r = await setMiResidencial({ telefono_ayuda: telefono.trim(), email_ayuda: email.trim() });
      const t = r.telefono_ayuda || "", e = r.email_ayuda || "";
      setTelefono(t); setEmail(e); setGuardado({ telefono: t, email: e });
      setMsg("✓ Contacto guardado. Los residentes ya lo ven en Ayuda.");
    } catch (e) {
      setError((e as Error).message || "No se pudo guardar");
    } finally {
      setGuardando(false);
    }
  }

  return (
    <div className="config-card">
      <div className="config-card-head">
        <span className="config-card-icon"><LifeBuoy size={18} /></span>
        <div className="config-card-titles">
          <h3>Ayuda para residentes</h3>
          <p>El teléfono y el correo que ven los residentes en la sección <b>Ayuda</b> de la app y del
            portal, para dudas, quejas y sugerencias.</p>
        </div>
      </div>
      {cargando ? <p className="muted small">Cargando…</p> : (
        <>
          <div className="config-grid-2 ay-cfg-grid">
            <div className="config-field">
              <label htmlFor="ay-tel">Teléfono de servicio al cliente</label>
              <input id="ay-tel" type="text" inputMode="tel" value={telefono} maxLength={30}
                onChange={e => setTelefono(e.target.value)} placeholder="Ej. 2550-1234 o +504 9999-0000" />
            </div>
            <div className="config-field">
              <label htmlFor="ay-mail">Correo para consultas</label>
              <input id="ay-mail" type="text" inputMode="email" value={email} maxLength={160}
                onChange={e => setEmail(e.target.value)} placeholder="Ej. administracion@villasdelsol.hn" />
            </div>
          </div>
          <p className="muted small" style={{ marginTop: 8 }}>
            Podés dejar uno solo. Si los dejás vacíos, la sección Ayuda le dice al residente que se acerque a la administración.
          </p>
          <div className="config-acciones">
            <button onClick={guardar} disabled={guardando || !cambio}>
              {guardando ? "Guardando…" : "Guardar contacto"}
            </button>
            {msg && <span className="ok" style={{ fontSize: 13 }}>{msg}</span>}
            {error && <span className="err" style={{ fontSize: 13 }}>{error}</span>}
          </div>
        </>
      )}
    </div>
  );
}

// ── Cuentas bancarias ──────────────────────────────────────────────────────
type Borrador = { banco: string; numero: string; titular: string; tipo: TipoCuentaBancaria | "" };
const VACIO: Borrador = { banco: "", numero: "", titular: "", tipo: "" };

export function CuentasBancariasPanel() {
  const [cuentas, setCuentas] = useState<CuentaBancariaDTO[]>([]);
  const [cargando, setCargando] = useState(true);
  // null = sin formulario abierto; "nueva" = agregando; un id = editando esa.
  const [editando, setEditando] = useState<string | null>(null);
  const [borrador, setBorrador] = useState<Borrador>(VACIO);
  const [quitando, setQuitando] = useState<string | null>(null);
  const [trabajando, setTrabajando] = useState(false);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    getCuentasBancarias().then(setCuentas)
      .catch(() => setError("No se pudieron cargar las cuentas"))
      .finally(() => setCargando(false));
  }, []);

  function abrir(c?: CuentaBancariaDTO) {
    setError(""); setMsg(""); setQuitando(null);
    if (c) {
      setEditando(c.id);
      setBorrador({ banco: c.banco, numero: c.numero, titular: c.titular || "", tipo: c.tipo || "" });
    } else {
      setEditando("nueva");
      setBorrador(VACIO);
    }
  }

  async function guardar() {
    if (!borrador.banco.trim()) { setError("Escribí el nombre del banco."); return; }
    if (!borrador.numero.trim()) { setError("Escribí el número de cuenta."); return; }
    setTrabajando(true); setError("");
    const body = { banco: borrador.banco.trim(), numero: borrador.numero.trim(),
                   titular: borrador.titular.trim(), tipo: borrador.tipo };
    try {
      if (editando === "nueva") {
        const c = await crearCuentaBancaria(body);
        setCuentas(cs => [...cs, c]);
        setMsg(`✓ Se agregó la cuenta de ${c.banco}.`);
      } else if (editando) {
        const c = await editarCuentaBancaria(editando, body);
        setCuentas(cs => cs.map(x => x.id === c.id ? c : x));
        setMsg("✓ Cuenta actualizada.");
      }
      setEditando(null);
    } catch (e) {
      setError((e as Error).message || "No se pudo guardar");
    } finally {
      setTrabajando(false);
    }
  }

  async function quitar(id: string) {
    setTrabajando(true); setError(""); setMsg("");
    try {
      await borrarCuentaBancaria(id);
      setCuentas(cs => cs.filter(x => x.id !== id));
      setQuitando(null);
      setMsg("✓ Cuenta quitada. Los residentes ya no la ven.");
    } catch (e) {
      setError((e as Error).message || "No se pudo quitar");
    } finally {
      setTrabajando(false);
    }
  }

  const formulario = (
    <div className="cb-form">
      <div className="cb-form-grid">
        <div className="config-field">
          <label htmlFor="cb-banco">Banco</label>
          <input id="cb-banco" type="text" list="cb-bancos" value={borrador.banco} maxLength={80} autoFocus
            onChange={e => setBorrador(b => ({ ...b, banco: e.target.value }))} placeholder="Ej. Banco Atlántida" />
          <datalist id="cb-bancos">{BANCOS_HN.map(b => <option key={b} value={b} />)}</datalist>
        </div>
        <div className="config-field">
          <label htmlFor="cb-numero">Número de cuenta</label>
          <input id="cb-numero" type="text" inputMode="numeric" value={borrador.numero} maxLength={40}
            onChange={e => setBorrador(b => ({ ...b, numero: e.target.value }))} placeholder="Ej. 1234-5678-90" />
        </div>
        <div className="config-field">
          <label htmlFor="cb-tipo">Tipo <span className="muted">(opcional)</span></label>
          <select id="cb-tipo" value={borrador.tipo}
            onChange={e => setBorrador(b => ({ ...b, tipo: e.target.value as Borrador["tipo"] }))}>
            <option value="">Sin indicar</option>
            <option value="ahorro">Ahorro</option>
            <option value="cheques">Cheques</option>
          </select>
        </div>
        <div className="config-field">
          <label htmlFor="cb-titular">A nombre de <span className="muted">(opcional)</span></label>
          <input id="cb-titular" type="text" value={borrador.titular} maxLength={120}
            onChange={e => setBorrador(b => ({ ...b, titular: e.target.value }))} placeholder="Ej. Patronato Villas del Sol" />
        </div>
      </div>
      <div className="config-acciones" style={{ marginTop: 14 }}>
        <button onClick={guardar} disabled={trabajando}>
          {trabajando ? "Guardando…" : editando === "nueva" ? "Agregar cuenta" : "Guardar cambios"}
        </button>
        <button className="ghost" onClick={() => { setEditando(null); setError(""); }} disabled={trabajando}>Cancelar</button>
      </div>
    </div>
  );

  return (
    <div className="config-card">
      <div className="config-card-head">
        <span className="config-card-icon"><Landmark size={18} /></span>
        <div className="config-card-titles">
          <h3>Cuentas para pagar</h3>
          <p>Las cuentas a las que los residentes pueden transferir o depositar sus cuotas. Las ven en la app y
            en el portal, junto a sus cuotas, con un botón para copiar el número.</p>
        </div>
      </div>

      {cargando ? <p className="muted small">Cargando…</p> : (
        <>
          {cuentas.length === 0 && editando !== "nueva" && (
            <div className="cb-vacio">
              <p><b>Todavía no hay cuentas.</b> Mientras no agregues ninguna, los residentes no ven a dónde
                transferir y tienen que preguntar.</p>
            </div>
          )}

          {cuentas.length > 0 && (
            <ul className="cb-admin-lista">
              {cuentas.map(c => (
                <li key={c.id}>
                  {editando === c.id ? formulario : (
                    <div className="cb-admin-fila">
                      <div className="cb-admin-datos">
                        <b>{c.banco}</b>
                        <span className="cb-admin-numero">{c.numero}</span>
                        <small>{[c.tipo && TIPO_CUENTA_TEXTO[c.tipo], c.titular && `A nombre de ${c.titular}`]
                          .filter(Boolean).join(" · ") || "Sin tipo ni titular"}</small>
                      </div>
                      {quitando === c.id ? (
                        <div className="cb-admin-acciones cb-confirmar">
                          <span>¿Quitar esta cuenta?</span>
                          <button className="mini cb-btn-peligro" onClick={() => quitar(c.id)} disabled={trabajando}>
                            <Check size={14} /> Sí, quitar
                          </button>
                          <button className="ghost mini" onClick={() => setQuitando(null)} disabled={trabajando}>
                            <X size={14} /> No
                          </button>
                        </div>
                      ) : (
                        <div className="cb-admin-acciones">
                          <button className="ghost mini" onClick={() => abrir(c)} disabled={trabajando || editando !== null}
                            aria-label={`Editar la cuenta de ${c.banco}`}><Pencil size={14} /> Editar</button>
                          <button className="ghost mini" onClick={() => { setQuitando(c.id); setMsg(""); }}
                            disabled={trabajando || editando !== null}
                            aria-label={`Quitar la cuenta de ${c.banco}`}><Trash2 size={14} /> Quitar</button>
                        </div>
                      )}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}

          {editando === "nueva" && formulario}

          {editando === null && cuentas.length < 10 && (
            <div className="config-acciones">
              <button onClick={() => abrir()}><Plus size={15} /> Agregar cuenta</button>
            </div>
          )}
          {msg && <p className="ok small" style={{ marginTop: 10 }}>{msg}</p>}
          {error && <p className="err small" style={{ marginTop: 10 }}>{error}</p>}
        </>
      )}
    </div>
  );
}
