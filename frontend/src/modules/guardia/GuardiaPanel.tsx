import { useState, useRef, useEffect } from "react";
import { validarQR, registrarAcceso, type VisitaDTO } from "../../api/client";

export function GuardiaPanel() {
  const [step, setStep] = useState<"scan" | "review" | "done">("scan");
  const [qrInput, setQrInput] = useState("");
  const [visita, setVisita] = useState<VisitaDTO | null>(null);
  const [direccion, setDireccion] = useState<"entrada" | "salida">("entrada");
  const [cuentaBloqueada, setCuentaBloqueada] = useState(false);
  const [error, setError] = useState("");
  const [fotoId, setFotoId] = useState("");
  const [fotoPlaca, setFotoPlaca] = useState("");
  const [fotoNumero, setFotoNumero] = useState("");
  const [procesando, setProcesando] = useState(false);
  const [resultado, setResultado] = useState("");
  const [escaneando, setEscaneando] = useState(false);
  const [tomandoFoto, setTomandoFoto] = useState<null | "id" | "placa" | "numero">(null);

  const videoRef = useRef<HTMLVideoElement>(null);
  const fotoVideoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const fotoStreamRef = useRef<MediaStream | null>(null);
  const animRef = useRef<number>(0);

  async function validar(token: string) {
    setError("");
    if (!token.trim()) { setError("Ingresa o escanea un codigo QR"); return; }
    try {
      const data = await validarQR(token.trim());
      setVisita(data.visita);
      setDireccion(data.direccion_sugerida || "entrada");
      setCuentaBloqueada(!!data.cuenta_bloqueada);
      setStep("review");
    } catch (e) { setError((e as Error).message); }
  }

  // ─── Escaneo de QR ───
  async function iniciarCamara() {
    setError(""); setEscaneando(true);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment" }
      });
      streamRef.current = stream;
      if (videoRef.current) { videoRef.current.srcObject = stream; videoRef.current.play(); }
      escanearFrames();
    } catch {
      setError("No se pudo abrir la camara. Verifica los permisos.");
      setEscaneando(false);
    }
  }

  function escanearFrames() {
    if (!("BarcodeDetector" in window)) {
      setError("Tu navegador no soporta escaneo. Usa el codigo manual.");
      detenerCamara(); return;
    }
    const detector = new (window as any).BarcodeDetector({ formats: ["qr_code"] });
    async function tick() {
      if (!videoRef.current || !streamRef.current) return;
      try {
        const codes = await detector.detect(videoRef.current);
        if (codes.length > 0) { detenerCamara(); await validar(codes[0].rawValue); return; }
      } catch {}
      animRef.current = requestAnimationFrame(tick);
    }
    animRef.current = requestAnimationFrame(tick);
  }

  function detenerCamara() {
    cancelAnimationFrame(animRef.current);
    if (streamRef.current) { streamRef.current.getTracks().forEach(t => t.stop()); streamRef.current = null; }
    setEscaneando(false);
  }

  // ─── Tomar foto INLINE (sin salir de la app) ───
  async function abrirCamaraFoto(cual: "id" | "placa" | "numero") {
    setError(""); setTomandoFoto(cual);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment" }
      });
      fotoStreamRef.current = stream;
      // pequeño delay para que el video element exista
      setTimeout(() => {
        if (fotoVideoRef.current) { fotoVideoRef.current.srcObject = stream; fotoVideoRef.current.play(); }
      }, 100);
    } catch {
      setError("No se pudo abrir la camara para la foto.");
      setTomandoFoto(null);
    }
  }

  function capturarFoto() {
    if (!fotoVideoRef.current) return;
    const video = fotoVideoRef.current;
    // Limitar a máx 1280px en el lado mayor: de sobra para leer DNI/placas,
    // y reduce 4-10x el peso de cada foto (sube más rápido en la caseta
    // y ahorra almacenamiento — son 3 fotos por cada acceso).
    const MAX_LADO = 1280;
    const escala = Math.min(1, MAX_LADO / Math.max(video.videoWidth, video.videoHeight));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(video.videoWidth * escala);
    canvas.height = Math.round(video.videoHeight * escala);
    canvas.getContext("2d")!.drawImage(video, 0, 0, canvas.width, canvas.height);
    const dataUrl = canvas.toDataURL("image/jpeg", 0.7);
    if (tomandoFoto === "id") setFotoId(dataUrl);
    else if (tomandoFoto === "placa") setFotoPlaca(dataUrl);
    else if (tomandoFoto === "numero") setFotoNumero(dataUrl);
    cerrarCamaraFoto();
  }

  function cerrarCamaraFoto() {
    if (fotoStreamRef.current) { fotoStreamRef.current.getTracks().forEach(t => t.stop()); fotoStreamRef.current = null; }
    setTomandoFoto(null);
  }

  useEffect(() => { return () => { detenerCamara(); cerrarCamaraFoto(); }; }, []);

  async function darAcceso() {
    if (!visita) return;
    setProcesando(true);
    try {
      const r = await registrarAcceso({
        visita_id: visita.id, direccion, acceso_id: 1,
        foto_identidad: direccion === "entrada" ? (fotoId || undefined) : undefined,
        foto_placa: direccion === "entrada" ? (fotoPlaca || undefined) : undefined,
        foto_numero_asignado: direccion === "entrada" ? (fotoNumero || undefined) : undefined,
      });
      setResultado(r.mensaje);
      setStep("done");
    } catch (e) { setError((e as Error).message); }
    finally { setProcesando(false); }
  }

  function reiniciar() {
    setStep("scan"); setQrInput(""); setVisita(null); setDireccion("entrada"); setCuentaBloqueada(false);
    setError(""); setFotoId(""); setFotoPlaca(""); setFotoNumero(""); setResultado("");
  }

  // ─── Pantalla de tomar foto inline ───
  if (tomandoFoto) {
    return (
      <div className="card wide guardia-panel">
        <h2>{tomandoFoto === "id" ? "Foto de identidad" : (tomandoFoto === "placa" ? "Foto de placa" : "Foto del número asignado")}</h2>
        <div className="foto-camara">
          <video ref={fotoVideoRef} autoPlay playsInline muted className="qr-video" />
          <div className="row-btns" style={{ marginTop: 12 }}>
            <button className="guardia-btn access" onClick={capturarFoto}>Tomar foto</button>
            <button className="ghost" onClick={cerrarCamaraFoto}>Cancelar</button>
          </div>
        </div>
        {error && <div className="error">{error}</div>}
      </div>
    );
  }

  return (
    <div className="card wide guardia-panel">
      <h2>Panel de Guardia</h2>

      {step === "scan" && (
        <div className="guardia-scan">
          {!escaneando ? (
            <>
              <button className="guardia-btn scan-cam" onClick={iniciarCamara}>Escanear con camara</button>
              <p className="muted" style={{ margin: "14px 0 6px" }}>o ingresa el código manualmente (QR o código de delivery):</p>
              <input className="guardia-input" placeholder="Código QR o código numérico de delivery"
                value={qrInput} onChange={e => setQrInput(e.target.value)}
                onKeyDown={e => e.key === "Enter" && validar(qrInput)} />
              <button className="ghost" onClick={() => validar(qrInput)}>Validar código manual</button>
            </>
          ) : (
            <>
              <video ref={videoRef} className="qr-video" autoPlay playsInline muted />
              <p className="muted">Apunta la camara al codigo QR</p>
              <button className="ghost" onClick={detenerCamara}>Cancelar</button>
            </>
          )}
          {error && <div className="error">{error}</div>}
        </div>
      )}

      {step === "review" && visita && (
        <div className="guardia-review">
          <div className={`visit-card ${direccion === "salida" ? "salida-box" : "ok-box"}`}>
            <span className={`pill big ${direccion === "salida" ? "amber" : "green"}`}>
              {direccion === "salida" ? "REGISTRAR SALIDA" : "QR VALIDO"}
            </span>
            <h3>{visita.nombre_visitante}</h3>
            <div className="visit-detail">
              {visita.documento_id && <div><span className="muted">Identidad:</span> <b>{visita.documento_id}</b></div>}
              {visita.empresa && <div><span className="muted">Empresa:</span> <b>{visita.empresa}</b></div>}
              {visita.en_vehiculo && <div><span className="muted">Placa:</span> <b>{visita.placa_vehiculo}</b></div>}
              <div><span className="muted">Tipo:</span> <b>{visita.tipo}</b></div>
              <div><span className="muted">Autorizado por:</span> <b>{visita.generada_por}</b></div>
            </div>
          </div>

          {cuentaBloqueada && (
            <div className="aviso-mora">
              ⚠️ <b>La cuenta del residente tiene mora.</b> El código es válido;
              queda a tu criterio autorizar el ingreso según las reglas de la residencial.
            </div>
          )}

          {direccion === "salida" ? (
            <div className="nota">
              Esta visita ya ingresó. Confirma su salida para liberar el registro.
            </div>
          ) : (
            <div className="guardia-fotos">
              <div className="foto-slot" onClick={() => abrirCamaraFoto("id")}>
                {fotoId ? <img src={fotoId} alt="ID" /> : <span className="foto-icon">Foto identidad</span>}
              </div>
              <div className="foto-slot" onClick={() => abrirCamaraFoto("placa")}>
                {fotoPlaca ? <img src={fotoPlaca} alt="Placa" /> : <span className="foto-icon">Foto placa</span>}
              </div>
              <div className="foto-slot" onClick={() => abrirCamaraFoto("numero")}>
                {fotoNumero ? <img src={fotoNumero} alt="Número" /> : <span className="foto-icon">Foto número asignado</span>}
              </div>
            </div>
          )}

          {error && <div className="error">{error}</div>}
          {direccion === "entrada" && !fotoId && (
            <div className="nota" style={{ background: "#fff7ed", borderColor: "#f5c98a" }}>
              📷 La foto de identidad es obligatoria para dar acceso.
            </div>
          )}
          {direccion === "entrada" && visita.en_vehiculo && !fotoPlaca && (
            <div className="nota" style={{ background: "#fff7ed", borderColor: "#f5c98a" }}>
              📷 La foto de la placa es obligatoria para vehículos.
            </div>
          )}
          <div className="row-btns">
            <button
              className={`guardia-btn ${direccion === "salida" ? "salida" : "access"}`}
              onClick={darAcceso}
              disabled={procesando || (direccion === "entrada" && (!fotoId || (visita.en_vehiculo && !fotoPlaca)))}
            >
              {procesando ? "Procesando..." : direccion === "salida" ? "Dar salida" : "Dar acceso"}
            </button>
            <button className="ghost" onClick={reiniciar}>Cancelar</button>
          </div>
        </div>
      )}

      {step === "done" && (
        <div className="guardia-done">
          <div className="done-icon">V</div>
          <h2>Acceso concedido</h2>
          <p>{resultado}</p>
          <p className="muted">Visitante: <b>{visita?.nombre_visitante}</b></p>
          <button className="guardia-btn" onClick={reiniciar}>Siguiente visita</button>
        </div>
      )}
    </div>
  );
}
