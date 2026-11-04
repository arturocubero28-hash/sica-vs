import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Camera, Image as ImageIcon, X } from "lucide-react";

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
    if (!camaraAbierta || !videoRef.current || !streamRef.current) return;
    const video = videoRef.current;
    video.srcObject = streamRef.current;
    // autoPlay basta en casi todos los navegadores, pero no en todos: si la
    // reproducción no arranca, el recuadro queda en negro y parece que la
    // cámara no abrió. Se pide explícitamente y se avisa si falla.
    video.play().catch(() => {
      setProblema("La cámara abrió pero el navegador no muestra la imagen. "
        + "Probá recargar la página.");
    });
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

  /// Día 73 — por qué cada error merece su propio mensaje.
  ///
  /// Antes esto tenía un solo mensaje para todo y, peor, cuando el
  /// navegador no exponía la cámara abría el explorador de archivos en
  /// silencio: desde afuera se veía como "le doy a tomar foto y no abre la
  /// cámara", sin ninguna pista de la causa. Las causas son distintas y
  /// cada una se arregla distinto, así que cada una lo dice.
  function _motivo(e: unknown): string {
    const nombre = (e as { name?: string })?.name || "";
    switch (nombre) {
      case "NotAllowedError":
      case "SecurityError":
        // Día 73 — este error tiene DOS causas que se ven idénticas desde
        // afuera, y una no depende de la persona: si el servidor manda la
        // cabecera Permissions-Policy con camera=(), el navegador bloquea la
        // cámara en todo el documento y ningún permiso que se conceda lo
        // cambia. La consola lo dice ("camera is not allowed in this
        // document"), pero nadie abre la consola, así que el mensaje nombra
        // las dos para que no se pierda media hora revisando el candado.
        return "El navegador bloqueó la cámara. Revisá que el candado de la barra " +
               "de direcciones tenga la cámara en «Permitir». Si ya está permitida, " +
               "el bloqueo viene del servidor: avisale a quien lo administra.";
      case "NotFoundError":
      case "OverconstrainedError":
        return "No se encontró ninguna cámara conectada a este equipo.";
      case "NotReadableError":
        return "La cámara está siendo usada por otro programa. Cerrá la otra " +
               "aplicación (Zoom, Teams, Meet) y volvé a intentar.";
      default:
        return `No se pudo abrir la cámara (${nombre || "motivo desconocido"}). ` +
               "Podés elegir una imagen del archivo.";
    }
  }

  async function abrirCamara() {
    setProblema("");

    // getUserMedia solo existe en páginas seguras. Si el panel se abre por
    // http:// o por una IP de la red local, el navegador ni siquiera lo
    // ofrece — y eso no es un permiso que se pueda conceder.
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      setProblema(
        "Este navegador no permite usar la cámara en esta dirección. Abrí el " +
        "panel por https:// (patronatovillasdelsol.com) o elegí una imagen del archivo.");
      return;
    }

    // Primero se pide la cámara trasera como PREFERENCIA, que en el teléfono
    // es la correcta para fotografiar a otra persona. Si el equipo no puede
    // cumplir la restricción, se reintenta sin pedir nada en particular
    // antes de darla por fallida: una webcam de escritorio no tiene "trasera".
    const intentos: MediaStreamConstraints[] = [
      { video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 }, height: { ideal: 960 } },
        audio: false },
      { video: true, audio: false },
    ];

    let ultimo: unknown = null;
    for (const restricciones of intentos) {
      try {
        streamRef.current = await navigator.mediaDevices.getUserMedia(restricciones);
        setCamaraAbierta(true);
        return;
      } catch (e) {
        ultimo = e;
        // Si la persona dijo que no, reintentar con otras restricciones solo
        // vuelve a molestarla con el mismo resultado.
        const nombre = (e as { name?: string })?.name || "";
        if (nombre === "NotAllowedError" || nombre === "SecurityError") break;
      }
    }
    setProblema(_motivo(ultimo));
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

      {problema && (
        <div className="captura-foto-problema" role="alert">
          <AlertTriangle size={15} />
          <span>{problema}</span>
        </div>
      )}
    </div>
  );
}
