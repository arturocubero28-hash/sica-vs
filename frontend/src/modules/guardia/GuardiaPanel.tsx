import { useState, useRef } from "react";
import { validarQR, registrarAcceso, type VisitaDTO } from "../../api/client";

/**
 * Panel del Guardia — optimizado para tablet/móvil.
 * Flujo: ingresar código QR → validar → ver datos → tomar fotos → dar acceso
 */
export function GuardiaPanel() {
  const [step, setStep] = useState<"scan" | "review" | "done">("scan");
  const [qrInput, setQrInput] = useState("");
  const [visita, setVisita] = useState<VisitaDTO | null>(null);
  const [error, setError] = useState("");
  const [fotoId, setFotoId] = useState("");
  const [fotoPlaca, setFotoPlaca] = useState("");
  const [procesando, setProcesando] = useState(false);
  const [resultado, setResultado] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  async function escanear() {
    setError("");
    const token = qrInput.trim();
    if (!token) { setError("Ingresa o escanea un código QR"); return; }
    try {
      const data = await validarQR(token);
      setVisita(data.visita);
      setStep("review");
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function darAcceso() {
    if (!visita) return;
    setProcesando(true);
    try {
      const r = await registrarAcceso({
        visita_id: visita.id,
        direccion: "entrada",
        acceso_id: 1,
        foto_identidad: fotoId || undefined,
        foto_placa: fotoPlaca || undefined,
      });
      setResultado(r.mensaje);
      setStep("done");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setProcesando(false);
    }
  }

  function reiniciar() {
    setStep("scan");
    setQrInput("");
    setVisita(null);
    setError("");
    setFotoId("");
    setFotoPlaca("");
    setResultado("");
    setTimeout(() => inputRef.current?.focus(), 100);
  }

  function capturarFoto(setter: (v: string) => void) {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "image/*";
    input.capture = "environment";
    input.onchange = () => {
      const file = input.files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => setter(reader.result as string);
      reader.readAsDataURL(file);
    };
    input.click();
  }

  return (
    <div className="card wide guardia-panel">
      <h2>Panel de Guardia</h2>

      {/* PASO 1: Escanear QR */}
      {step === "scan" && (
        <div className="guardia-scan">
          <p className="muted">Ingresa el código QR de la visita:</p>
          <input
            ref={inputRef}
            className="guardia-input"
            placeholder="Pega o escanea el código QR aquí"
            value={qrInput}
            onChange={e => setQrInput(e.target.value)}
            onKeyDown={e => e.key === "Enter" && escanear()}
            autoFocus
          />
          {error && <div className="error">{error}</div>}
          <button className="guardia-btn" onClick={escanear}>Validar código</button>
        </div>
      )}

      {/* PASO 2: Revisar datos y tomar fotos */}
      {step === "review" && visita && (
        <div className="guardia-review">
          <div className="visit-card ok-box">
            <span className="pill green big">QR VÁLIDO</span>
            <h3>{visita.nombre_visitante}</h3>
            <div className="visit-detail">
              {visita.documento_id && <div><span className="muted">Identidad:</span> <b>{visita.documento_id}</b></div>}
              {visita.empresa && <div><span className="muted">Empresa:</span> <b>{visita.empresa}</b></div>}
              {visita.en_vehiculo && <div><span className="muted">Placa:</span> <b>{visita.placa_vehiculo}</b></div>}
              <div><span className="muted">Tipo:</span> <b>{visita.tipo}</b></div>
              <div><span className="muted">Generado por:</span> <b>{visita.generada_por}</b></div>
            </div>
          </div>

          <div className="guardia-fotos">
            <div className="foto-slot" onClick={() => capturarFoto(setFotoId)}>
              {fotoId ? <img src={fotoId} alt="ID" /> : <><span className="foto-icon">📷</span><span>Foto identidad</span></>}
            </div>
            <div className="foto-slot" onClick={() => capturarFoto(setFotoPlaca)}>
              {fotoPlaca ? <img src={fotoPlaca} alt="Placa" /> : <><span className="foto-icon">🚗</span><span>Foto placa</span></>}
            </div>
          </div>

          {error && <div className="error">{error}</div>}

          <div className="row-btns">
            <button className="guardia-btn access" onClick={darAcceso} disabled={procesando}>
              {procesando ? "Procesando..." : "✓ Dar acceso"}
            </button>
            <button className="ghost" onClick={reiniciar}>Cancelar</button>
          </div>
        </div>
      )}

      {/* PASO 3: Acceso concedido */}
      {step === "done" && (
        <div className="guardia-done">
          <div className="done-icon">✓</div>
          <h2>Acceso concedido</h2>
          <p>{resultado}</p>
          <p className="muted">Visitante: <b>{visita?.nombre_visitante}</b></p>
          <button className="guardia-btn" onClick={reiniciar}>Siguiente visita</button>
        </div>
      )}
    </div>
  );
}
