import { useState, useEffect, useCallback } from "react";
import {
  listarAutorizadores, crearAutorizador, desactivarAutorizador,
  historialProveedores, urlFotoGuardia,
  type AutorizadorDTO, type AccesoProveedorDTO,
} from "../../api/client";
import { Truck, UserCheck, Trash2, Plus, Image as ImageIcon } from "lucide-react";

/**
 * Panel de Proveedores — Día 69.
 *
 * POR QUÉ ES UNA SECCIÓN APARTE
 * -----------------------------
 * Un camión de agua, de gas o de refrescos no es una visita: nadie lo
 * invitó desde la app, no tiene QR y no pertenece a una casa. Antes del
 * Día 69 el guardia lo dejaba entrar con una apertura manual, que registra
 * que SE ABRIÓ la tranca pero no quién entró ni con permiso de quién.
 *
 * Como estos accesos no tienen visita asociada, tampoco aparecen en el
 * reporte de visitas (que parte de la tabla de visitas). De ahí que tengan
 * su propio historial y no una fila más en el de siempre: ahí la mitad de
 * las columnas saldrían vacías.
 *
 * LOS DOS PEDAZOS DE ESTA PANTALLA
 * --------------------------------
 * 1. Autorizadores: la lista cerrada de quién puede dar el permiso por
 *    parte del patronato. El guardia elige de esta lista y no puede
 *    escribir texto libre — si pudiera, el dato no serviría para auditar
 *    nada, que es justamente para lo que se guarda.
 * 2. Historial: cada entrada con empresa, conductor, placa, tranca, qué
 *    guardia abrió y quién autorizó.
 */

function MsgBanner({ msg, onClose }: {
  msg: { tipo: "ok" | "err"; texto: string } | null; onClose?: () => void;
}) {
  if (!msg) return null;
  return (
    <div className={`msg-banner msg-banner-${msg.tipo}`} role="alert">
      <span>{msg.tipo === "err" ? "⚠ " : "✓ "}{msg.texto}</span>
      {onClose && <button className="msg-banner-close" onClick={onClose}>✕</button>}
    </div>
  );
}

function fechaHora(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("es-HN", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

export function ProveedoresPanel() {
  const [tab, setTab] = useState<"historial" | "autorizadores">("historial");
  const [msg, setMsg] = useState<{ tipo: "ok" | "err"; texto: string } | null>(null);

  return (
    <div className="proveedores-panel">
      <div className="lista-head">
        <h2>Proveedores</h2>
      </div>
      <p className="muted small" style={{ marginTop: -4, marginBottom: 14, maxWidth: 700 }}>
        Camiones de agua, gas, refrescos y servicios públicos. No entran con QR,
        así que el guardia los registra a mano y cada entrada queda con quién
        venía, en qué vehículo y quién autorizó el ingreso por parte del patronato.
      </p>

      {msg && (
        <div style={{ position: "sticky", top: 8, zIndex: 20, marginBottom: 12 }}>
          <MsgBanner msg={msg} onClose={() => setMsg(null)} />
        </div>
      )}

      <div className="tabs">
        <button className={tab === "historial" ? "tab on" : "tab"}
          onClick={() => setTab("historial")}>
          Historial de entradas
        </button>
        <button className={tab === "autorizadores" ? "tab on" : "tab"}
          onClick={() => setTab("autorizadores")}>
          Quién puede autorizar
        </button>
      </div>

      {tab === "historial"
        ? <Historial onError={t => setMsg({ tipo: "err", texto: t })} />
        : <Autorizadores onMsg={setMsg} />}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// HISTORIAL
// ─────────────────────────────────────────────────────────────────────────
function Historial({ onError }: { onError: (t: string) => void }) {
  const [filas, setFilas] = useState<AccesoProveedorDTO[]>([]);
  const [cargando, setCargando] = useState(true);
  const [buscar, setBuscar] = useState("");
  const [desde, setDesde] = useState("");
  const [hasta, setHasta] = useState("");
  const [pagina, setPagina] = useState(1);
  const [totalPaginas, setTotalPaginas] = useState(1);
  const [total, setTotal] = useState(0);

  const cargar = useCallback(() => {
    setCargando(true);
    historialProveedores({ buscar, desde, hasta, pagina })
      .then(r => {
        setFilas(r.eventos);
        setTotalPaginas(r.total_paginas || 1);
        setTotal(r.total || 0);
      })
      .catch(e => onError((e as Error).message))
      .finally(() => setCargando(false));
  }, [buscar, desde, hasta, pagina, onError]);

  // La búsqueda y las fechas se mandan al servidor, así que se espera un
  // momento antes de disparar: si no, cada tecla sería una consulta.
  useEffect(() => {
    const t = setTimeout(cargar, 300);
    return () => clearTimeout(t);
  }, [cargar]);

  // Al cambiar un filtro se vuelve a la página 1. Sin esto, filtrar estando
  // en la página 4 puede dejar la tabla vacía sin explicación.
  useEffect(() => { setPagina(1); }, [buscar, desde, hasta]);

  return (
    <div className="lista-card">
      <div className="casas-filtros" style={{ flexWrap: "wrap", gap: 10 }}>
        <input className="casas-buscar" placeholder="Buscar por empresa, conductor o placa…"
          value={buscar} onChange={e => setBuscar(e.target.value)} />
        <label className="muted small" style={{ display: "flex", alignItems: "center", gap: 6 }}>
          Desde
          <input type="date" value={desde} onChange={e => setDesde(e.target.value)} />
        </label>
        <label className="muted small" style={{ display: "flex", alignItems: "center", gap: 6 }}>
          Hasta
          <input type="date" value={hasta} onChange={e => setHasta(e.target.value)} />
        </label>
      </div>
      <div className="casas-contador muted small">
        {total} entrada(s) de proveedores
        {totalPaginas > 1 && ` · página ${pagina} de ${totalPaginas}`}
      </div>

      {cargando ? <p className="muted">Cargando…</p> : filas.length === 0 ? (
        <div className="cuota-vacia">
          <Truck size={28} className="cuota-vacia-icon" />
          <p className="muted">
            {buscar || desde || hasta
              ? "Ningún acceso coincide con el filtro."
              : "Todavía no hay entradas de proveedores registradas. Aparecen acá en cuanto el guardia registre la primera desde su app."}
          </p>
        </div>
      ) : (
        <div className="scroll-x">
          <table className="data">
            <thead>
              <tr>
                <th>Fecha y hora</th>
                <th>Empresa</th>
                <th>Conductor</th>
                <th>Placa</th>
                <th>Tranca</th>
                <th>Guardia</th>
                <th>Autorizó</th>
                <th>ID</th>
              </tr>
            </thead>
            <tbody>
              {filas.map(f => (
                <tr key={f.id}>
                  <td style={{ whiteSpace: "nowrap" }}>{fechaHora(f.ocurrido_en)}</td>
                  <td><strong>{f.empresa}</strong></td>
                  <td>{f.conductor}</td>
                  <td>{f.placa || "—"}</td>
                  <td>
                    {f.tranca || "—"}
                    {f.punto_acceso && (
                      <div className="muted small">{f.punto_acceso}</div>
                    )}
                  </td>
                  <td>{f.guardia}</td>
                  <td>
                    {/* Si quedó sin autorizador, se dice. Una celda vacía se
                        lee como "no se cargó el dato"; un aviso se lee como
                        lo que es: un acceso sin respaldo del patronato. */}
                    {f.autorizado_por ? (
                      <>
                        {f.autorizado_por}
                        {f.autorizado_por_cargo && (
                          <div className="muted small">{f.autorizado_por_cargo}</div>
                        )}
                      </>
                    ) : <span className="pill amber">sin autorizador</span>}
                  </td>
                  <td>
                    {f.foto_identidad ? (
                      <button className="btn-tabla btn-tabla-ver"
                        onClick={() => window.open(urlFotoGuardia(f.foto_identidad!), "_blank")}>
                        <ImageIcon size={14} /> Ver
                      </button>
                    ) : <span className="muted small">sin foto</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {totalPaginas > 1 && (
        <div className="paginacion">
          <button className="ghost mini" disabled={pagina <= 1}
            onClick={() => setPagina(p => Math.max(1, p - 1))}>← Anterior</button>
          <span className="muted small">Página {pagina} de {totalPaginas} · {total} entradas</span>
          <button className="ghost mini" disabled={pagina >= totalPaginas}
            onClick={() => setPagina(p => Math.min(totalPaginas, p + 1))}>Siguiente →</button>
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// AUTORIZADORES
// ─────────────────────────────────────────────────────────────────────────
function Autorizadores({ onMsg }: {
  onMsg: (m: { tipo: "ok" | "err"; texto: string }) => void;
}) {
  const [lista, setLista] = useState<AutorizadorDTO[]>([]);
  const [cargando, setCargando] = useState(true);
  const [nombre, setNombre] = useState("");
  const [cargo, setCargo] = useState("");
  const [guardando, setGuardando] = useState(false);

  function recargar() {
    setCargando(true);
    listarAutorizadores()
      .then(setLista)
      .catch(e => onMsg({ tipo: "err", texto: (e as Error).message }))
      .finally(() => setCargando(false));
  }
  useEffect(() => { recargar(); }, []);

  async function agregar(e: React.FormEvent) {
    e.preventDefault();
    const n = nombre.trim();
    if (!n) return;
    setGuardando(true);
    try {
      await crearAutorizador({ nombre: n, cargo: cargo.trim() || undefined });
      setNombre(""); setCargo("");
      onMsg({ tipo: "ok", texto: `${n} ya puede autorizar entradas de proveedores.` });
      recargar();
    } catch (err) {
      onMsg({ tipo: "err", texto: (err as Error).message });
    } finally {
      setGuardando(false);
    }
  }

  async function quitar(a: AutorizadorDTO) {
    if (!confirm(
      `¿Quitar a ${a.nombre} de la lista?\n\n` +
      `No se borra: las entradas que ya autorizó siguen mostrando su nombre ` +
      `en el historial. Solo deja de aparecer en la app del guardia.`
    )) return;
    try {
      await desactivarAutorizador(a.id);
      onMsg({ tipo: "ok", texto: `${a.nombre} ya no aparece en la app del guardia.` });
      recargar();
    } catch (err) {
      onMsg({ tipo: "err", texto: (err as Error).message });
    }
  }

  return (
    <div className="lista-card">
      <p className="muted small" style={{ marginBottom: 14, maxWidth: 640 }}>
        Estas son las personas del patronato que pueden autorizar la entrada de
        un proveedor. El guardia elige de esta lista; no puede escribir un nombre
        a mano. Si la lista está vacía, no va a poder registrar ninguna entrada
        de proveedor.
      </p>

      <form onSubmit={agregar}
        style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 18 }}>
        <input placeholder="Nombre y apellido" value={nombre}
          onChange={e => setNombre(e.target.value)} required maxLength={120} />
        <input placeholder="Cargo (opcional). Ej: Presidente" value={cargo}
          onChange={e => setCargo(e.target.value)} maxLength={120} />
        <button className="btn-accion" type="submit" disabled={guardando || !nombre.trim()}>
          <Plus size={15} /> {guardando ? "Agregando…" : "Agregar"}
        </button>
      </form>

      {cargando ? <p className="muted">Cargando…</p> : lista.length === 0 ? (
        <div className="cuota-vacia">
          <UserCheck size={28} className="cuota-vacia-icon" />
          <p className="muted">
            Todavía no hay nadie en la lista. Mientras esté vacía, el guardia
            no puede registrar entradas de proveedores — su pantalla le va a
            decir que te pida cargar los autorizadores.
          </p>
        </div>
      ) : (
        <div className="scroll-x">
          <table className="data">
            <thead>
              <tr><th>Nombre</th><th>Cargo</th><th></th></tr>
            </thead>
            <tbody>
              {lista.map(a => (
                <tr key={a.id}>
                  <td><strong>{a.nombre}</strong></td>
                  <td>{a.cargo || <span className="muted small">—</span>}</td>
                  <td style={{ textAlign: "right" }}>
                    <button className="btn-tabla btn-tabla-baja" title="Quitar de la lista"
                      onClick={() => quitar(a)}>
                      <Trash2 size={14} /> Quitar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
