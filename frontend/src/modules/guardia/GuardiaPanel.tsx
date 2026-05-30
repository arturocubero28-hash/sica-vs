import { useState, useRef, useEffect } from "react";
import { Html5Qrcode } from "html5-qrcode";
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
  const [escaneando, setEscaneando] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const scannerRef = useRef<Html5Qrcode | null>(null);

  // Validar un token (venga de cámara o manual)
  async function validar(token: string) {
    setError("");
    if (!token.trim()) { setError("Ingresa o escanea un código QR"); return; }
    try {
      const data = await validarQR(token.trim());
      setVisita(data.visita);
      setStep("review");
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function escanear() {
    await validar(qrInput);
  }

  // Iniciar la cámara para escanear
  async function iniciarCamara() {
    setError("");
    setEscaneando(true);
    try {
      const scanner = new Html5Qrcode("qr-reader");
      scannerRef.current = scanner;
      await scanner.start(
        { facingMode: "environment" },  // cámara trasera
        { fps: 10, qrbox: { width: 250, height: 250 } },
        async (decodedText) => {
          await detenerCamara();
          await validar(decodedText);
        },
        () => { /* ignorar errores de frame sin QR */ }
      );
    } catch (e) {
      setError("No se pudo abrir la cámara. Verifica los permisos o usa el código manual.");
      setEscaneando(false);
    }
  }

  async function detenerCamara() {
    if (scannerRef.current) {
      try { await scannerRef.current.stop(); } catch { /* ya detenido */ }
      scannerRef.current = null;
    }
    setEscaneando(false);
  }

  // Limpiar cámara al desmontar
  useEffect(() => {
    return () => { if (scannerRef.current) scannerRef.current.stop().catch(() => {}); };
  }, []);

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
          {!escaneando ? (
            <>
              <button className="guardia-btn scan-cam" onClick={iniciarCamara}>
                📷 Escanear con cámara
              </button>
              <p className="muted" style={{ margin: "14px 0 6px" }}>o ingresá el código manualmente:</p>
              <input
                ref={inputRef}
                className="guardia-input"
                placeholder="Código QR de la visita"
                value={qrInput}
                onChange={e => setQrInput(e.target.value)}
                onKeyDown={e => e.key === "Enter" && escanear()}
              />
              <button className="ghost" onClick={escanear}>Validar código manual</button>
            </>
          ) : (
            <>
              <div id="qr-reader" className="qr-reader"></div>
              <p className="muted">Apuntá la cámara al código QR del visitante</p>
              <button className="ghost" onClick={detenerCamara}>Cancelar escaneo</button>
            </>
          )}
          {error && <div className="error">{error}</div>}
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
