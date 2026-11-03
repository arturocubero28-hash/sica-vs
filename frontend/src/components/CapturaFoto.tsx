import { useEffect, useRef, useState } from "react";
import { Camera, Image as ImageIcon, X } from "lucide-react";

/**
 * Día 72 — captura de la foto del residente desde el panel web.
 *
 * Es la foto contra la que el guardia compara la identificación cuando
 * alguien llega al portón sin teléfono, así que tiene que tomarse en el
 * momento del alta y no quedar para después.
 *
 * Dos caminos, según dónde esté abierto el panel:
 *   - "Tomar foto" abre la cámara del equipo con getUserMedia. Funciona
 *     igual con la webcam de la PC de administración y con la cámara del
 *     teléfono, y muestra la imagen en vivo antes de capturar.
 *   - "Elegir imagen" abre el selector de archivos. En el teléfono, el
 *     atributo capture hace que el sistema ofrezca la cámara directo.
 *
 * getUserMedia solo existe en HTTPS (producción lo es) y puede estar
 * bloqueado por permisos; si falla, se cae al selector de archivos en vez
 * de dejar a la persona sin forma de poner la foto.
 */
type Props = {
  valor: File | null;
  onCambio: (archivo: File | null) => void;
  /** Marca el recuadro en rojo cuando falta y ya se intentó guardar. */
  error?: boolean;
};

export function CapturaFoto({ valor, onCambio, error }: Props) {
  const [preview, setPreview] = useState<string | null>(null);
  const [camaraAbierta, setCamaraAbierta] = useState(false);
  const [problema, setProblema] = useState("");
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const archivoRef = useRef<HTMLInputElement | null>(null);

  // Vista previa del archivo elegido. Se libera la URL al cambiarla para
  // no dejar objetos colgando en memoria.
  useEffect(() => {
    if (!valor) { setPreview(null); return; }
    const url = URL.createObjectURL(valor);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [valor]);

  // El <video> recién existe cuando la cámara está abierta, así que el
  // stream se engancha acá y no dentro de abrirCamara().
  useEffect(() => {
    if (camaraAbierta && videoRef.current && streamRef.current) {
      videoRef.current.srcObject = streamRef.current;
    }
  }, [camaraAbierta]);

  // Apagar la cámara si se cierra el formulario con la cámara encendida:
  // sin esto queda la luz del equipo prendida.
  useEffect(() => () => {
    streamRef.current?.getTracks().forEach(t => t.stop());
    streamRef.current = null;
  }, []);

  function cerrarCamara() {
    streamRef.current?.getTracks().forEach(t => t.stop());
    streamRef.current = null;
    setCamaraAbierta(false);
  }

  async function abrirCamara() {
    setProblema("");
    if (!navigator.mediaDevices?.getUserMedia) {
      archivoRef.current?.click();
      return;
    }
    try {
      streamRef.current = await navigator.mediaDevices.getUserMedia({
        // "environment" como preferencia, no como exigencia: en el teléfono
        // elige la cámara trasera, que es con la que administración le toma
        // la foto al residente, y en una PC con una sola webcam el ideal
        // simplemente se ignora en vez de fallar.
        video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 }, height: { ideal: 960 } },
        audio: false,
      });
      setCamaraAbierta(true);
    } catch {
      setProblema("No se pudo abrir la cámara. Revisá el permiso del navegador o elegí una imagen.");
    }
  }

  function capturar() {
    const video = videoRef.current;
    if (!video || !video.videoWidth) return;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d")?.drawImage(video, 0, 0);
    canvas.toBlob(blob => {
      if (!blob) { setProblema("No se pudo capturar la imagen. Intentá de nuevo."); return; }
      onCambio(new File([blob], `foto-${Date.now()}.jpg`, { type: "image/jpeg" }));
      cerrarCamara();
    }, "image/jpeg", 0.9);
  }

  return (
    <div className={`captura-foto ${error ? "captura-foto--error" : ""}`}>
      <div className="captura-foto-marco">
        {camaraAbierta ? (
          <video ref={videoRef} autoPlay playsInline muted />
        ) : preview ? (
          <img src={preview} alt="Foto del titular" />
        ) : (
          <div className="captura-foto-vacia"><Camera size={26} /></div>
        )}
      </div>

      <div className="captura-foto-acciones">
        {camaraAbierta ? (
          <>
            <button type="button" className="mini" onClick={capturar}>
              <Camera size={14} /> Capturar
            </button>
            <button type="button" className="ghost mini" onClick={cerrarCamara}>
              <X size={14} /> Cancelar
            </button>
          </>
        ) : (
          <>
            <button type="button" className="mini" onClick={abrirCamara}>
              <Camera size={14} /> {valor ? "Tomar otra" : "Tomar foto"}
            </button>
            <button type="button" className="ghost mini" onClick={() => archivoRef.current?.click()}>
              <ImageIcon size={14} /> Elegir imagen
            </button>
            {valor && (
              <button type="button" className="ghost mini" onClick={() => onCambio(null)}>
                <X size={14} /> Quitar
              </button>
            )}
          </>
        )}
        <input ref={archivoRef} type="file" accept="image/*" capture="environment"
          style={{ display: "none" }}
          onChange={e => {
            const f = e.target.files?.[0];
            if (f) { onCambio(f); setProblema(""); }
            e.target.value = "";  // permite volver a elegir el mismo archivo
          }} />
      </div>

      {problema && <span className="campo-error">{problema}</span>}
    </div>
  );
}
