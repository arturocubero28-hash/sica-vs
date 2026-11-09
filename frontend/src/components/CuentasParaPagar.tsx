import { useEffect, useState } from "react";
import { Copy, Check, Landmark } from "lucide-react";
import { getCuentasBancarias, type CuentaBancariaDTO } from "../api/client";
import { copiarTexto, soloDigitos } from "../utils/copiar";

/* Día 76 — las cuentas a las que el residente puede transferir su cuota,
   con un botón para copiar el número (solo los dígitos, que es como lo
   pide la app del banco). Si el admin no configuró ninguna, no se muestra.

   compacta: versión para dentro del formulario de pago (sin título grande). */

const TIPO: Record<string, string> = { ahorro: "Ahorro", cheques: "Cheques" };

export function CuentasParaPagar({ compacta = false }: { compacta?: boolean }) {
  const [cuentas, setCuentas] = useState<CuentaBancariaDTO[]>([]);

  useEffect(() => {
    getCuentasBancarias().then(setCuentas).catch(() => { /* sin cuentas: no se muestra nada */ });
  }, []);

  if (cuentas.length === 0) return null;

  return (
    <section className={`cb-res ${compacta ? "cb-res--compacta" : ""}`} aria-label="Cuentas para pagar">
      {compacta ? (
        <p className="cb-res-intro"><Landmark size={15} /> ¿A dónde transferir? Copiá el número y pegalo en la app de tu banco.</p>
      ) : (
        <header className="cb-res-cabeza">
          <h3><Landmark size={18} /> Cuentas para pagar</h3>
          <p>Transferí o depositá a cualquiera de estas cuentas y después subí el comprobante en la cuota.</p>
        </header>
      )}
      <ul className="cb-res-lista">
        {cuentas.map(c => <FilaCuenta key={c.id} cuenta={c} />)}
      </ul>
    </section>
  );
}

function FilaCuenta({ cuenta }: { cuenta: CuentaBancariaDTO }) {
  const [copiado, setCopiado] = useState<"" | "ok" | "error">("");

  async function copiar() {
    const ok = await copiarTexto(soloDigitos(cuenta.numero));
    setCopiado(ok ? "ok" : "error");
    window.setTimeout(() => setCopiado(""), 2200);
  }

  const detalle = [cuenta.tipo && TIPO[cuenta.tipo], cuenta.titular].filter(Boolean).join(" · ");
  return (
    <li className="cb-res-fila">
      <div className="cb-res-datos">
        <span className="cb-res-banco">{cuenta.banco}</span>
        <span className="cb-res-numero">{cuenta.numero}</span>
        {detalle && <span className="cb-res-detalle">{detalle}</span>}
      </div>
      <button type="button" className={`cb-res-copiar ${copiado === "ok" ? "hecho" : ""}`} onClick={copiar}
        aria-label={`Copiar el número de cuenta de ${cuenta.banco}`}>
        {copiado === "ok" ? <><Check size={16} /> Copiado</>
          : copiado === "error" ? "No se pudo"
          : <><Copy size={16} /> Copiar</>}
      </button>
      <span className="sr-only" aria-live="polite">{copiado === "ok" ? "Número copiado" : ""}</span>
    </li>
  );
}
