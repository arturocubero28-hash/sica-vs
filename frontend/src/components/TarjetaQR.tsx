import { useEffect, useRef, useState } from "react";
import QRCode from "qrcode";
import type { VisitaDTO } from "../api/client";

/**
 * Renderiza la tarjeta QR completa en el CLIENTE usando Canvas.
 *
 * Antes esta tarjeta se generaba en el servidor (PIL/Pillow), lo que costaba
 * ~150ms de CPU por cada apertura del QR y no tenía caché — un residente que
 * abría, cerraba y volvía a abrir su QR disparaba tres renders completos de
 * una imagen de 2.1 megapíxeles. Con 500 familias eso saturaba los workers de
 * Gunicorn en las horas pico.
 *
 * Ahora el token del QR (que ya viajaba en el JSON de la visita) se renderiza
 * localmente. El servidor no toca una sola imagen. La tarjeta es idéntica.
 */

const AZUL = "#022E45";
const NARANJA = "#F48723";
const BLANCO = "#FFFFFF";

const TIPOS: Record<string, string> = {
  unica: "VISITA ÚNICA",
  recurrente: "VISITA RECURRENTE",
  repartidor: "REPARTIDOR",
};

// Mismas proporciones que la tarjeta original del servidor (600×880 @2x)
const ESCALA = 2;
const W = 600 * ESCALA;
const H = 880 * ESCALA;

function roundRect(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, w: number, h: number, r: number
) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

export async function generarTarjetaQR(visita: VisitaDTO): Promise<Blob | null> {
  if (!visita.qr_token) return null;

  const canvas = document.createElement("canvas");
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;

  // 1. Lienzo blanco
  ctx.fillStyle = BLANCO;
  ctx.fillRect(0, 0, W, H);

  // 2. Encabezado con degradado naranja
  const headH = 175 * ESCALA;
  const grad = ctx.createLinearGradient(0, 0, 0, headH);
  grad.addColorStop(0, "rgb(244,135,35)");
  grad.addColorStop(1, "rgb(255,190,110)");
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, W, headH);

  // 3. Logo en círculo blanco (si carga; si no, se omite sin romper)
  const cx = 70 * ESCALA;
  const cy = headH / 2;
  const rad = 58 * ESCALA;
  ctx.fillStyle = BLANCO;
  ctx.beginPath();
  ctx.arc(cx, cy, rad, 0, Math.PI * 2);
  ctx.fill();
  try {
    const logo = await cargarImagen("/logo-vs.png");
    const sz = 105 * ESCALA;
    ctx.drawImage(logo, cx - sz / 2, cy - sz / 2, sz, sz);
  } catch { /* sin logo, el círculo blanco queda igual */ }

  // 4. Texto del encabezado
  ctx.fillStyle = BLANCO;
  ctx.textAlign = "left";
  ctx.textBaseline = "middle";
  ctx.font = `bold ${24 * ESCALA}px Arial, sans-serif`;
  ctx.fillText("RESIDENCIAL", 150 * ESCALA, 58 * ESCALA);
  ctx.font = `bold ${32 * ESCALA}px Arial, sans-serif`;
  ctx.fillText("VILLAS DEL SOL", 150 * ESCALA, 105 * ESCALA);

  // 5. QR centrado con marco naranja
  const qrSize = 380 * ESCALA;
  const qrX = (W - qrSize) / 2;
  const qrY = headH + 40 * ESCALA;

  const qrDataUrl = await QRCode.toDataURL(visita.qr_token, {
    errorCorrectionLevel: "H",
    margin: 2,
    width: qrSize,
    color: { dark: AZUL, light: BLANCO },
  });
  const qrImg = await cargarImagen(qrDataUrl);
  ctx.drawImage(qrImg, qrX, qrY, qrSize, qrSize);

  ctx.strokeStyle = NARANJA;
  ctx.lineWidth = 5 * ESCALA;
  roundRect(ctx,
    qrX - 16 * ESCALA, qrY - 16 * ESCALA,
    qrSize + 32 * ESCALA, qrSize + 32 * ESCALA,
    24 * ESCALA);
  ctx.stroke();

  // 6. Línea separadora
  let y = qrY + qrSize + 50 * ESCALA;
  ctx.strokeStyle = "rgb(230,230,230)";
  ctx.lineWidth = 2 * ESCALA;
  ctx.beginPath();
  ctx.moveTo(80 * ESCALA, y);
  ctx.lineTo(W - 80 * ESCALA, y);
  ctx.stroke();
  y += 35 * ESCALA;

  // 7. Nombre del visitante (truncado si no cabe)
  ctx.textAlign = "center";
  ctx.fillStyle = AZUL;
  ctx.font = `bold ${34 * ESCALA}px Arial, sans-serif`;
  ctx.fillText(truncar(ctx, visita.nombre_visitante, W - 60 * ESCALA), W / 2, y);
  y += 50 * ESCALA;

  // 8. Pill naranja con el tipo de visita
  const tipoTxt = TIPOS[visita.tipo] ?? visita.tipo.toUpperCase();
  ctx.font = `bold ${19 * ESCALA}px Arial, sans-serif`;
  const tw = ctx.measureText(tipoTxt).width;
  const pillW = tw + 50 * ESCALA;
  ctx.fillStyle = NARANJA;
  roundRect(ctx, (W - pillW) / 2, y - 18 * ESCALA, pillW, 36 * ESCALA, 18 * ESCALA);
  ctx.fill();
  ctx.fillStyle = BLANCO;
  ctx.fillText(tipoTxt, W / 2, y);
  y += 50 * ESCALA;

  // 9. Detalles opcionales
  ctx.fillStyle = "rgb(90,90,90)";
  ctx.font = `${17 * ESCALA}px Arial, sans-serif`;
  if (visita.valido_hasta) {
    const d = new Date(visita.valido_hasta);
    const fmt = `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} a las ${pad(d.getHours())}:${pad(d.getMinutes())}`;
    ctx.fillText(`Válido hasta: ${fmt}`, W / 2, y);
    y += 32 * ESCALA;
  }
  if (visita.placa_vehiculo) {
    ctx.fillText(`Vehículo: ${visita.placa_vehiculo}`, W / 2, y);
    y += 32 * ESCALA;
  }
  if (visita.empresa) {
    ctx.fillText(`Empresa: ${visita.empresa}`, W / 2, y);
    y += 32 * ESCALA;
  }

  // 10. Pie de página
  ctx.fillStyle = "rgb(150,150,150)";
  ctx.font = `${15 * ESCALA}px Arial, sans-serif`;
  ctx.fillText("Presente este código al guardia en la entrada", W / 2, H - 45 * ESCALA);

  // 11. Franja inferior naranja
  ctx.fillStyle = NARANJA;
  ctx.fillRect(0, H - 14 * ESCALA, W, 14 * ESCALA);

  return new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
}

function pad(n: number) { return String(n).padStart(2, "0"); }

/** Recorta el texto con elipsis si excede el ancho disponible del canvas. */
function truncar(ctx: CanvasRenderingContext2D, texto: string, maxAncho: number): string {
  if (ctx.measureText(texto).width <= maxAncho) return texto;
  let recortado = texto;
  while (recortado.length > 1 && ctx.measureText(recortado + "…").width > maxAncho) {
    recortado = recortado.slice(0, -1);
  }
  return recortado + "…";
}

function cargarImagen(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new window.Image();
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = src;
  });
}

/** Componente que muestra la tarjeta QR renderizada en el cliente. */
export function TarjetaQR({ visita, className }: { visita: VisitaDTO; className?: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const urlRef = useRef<string | null>(null);

  useEffect(() => {
    let cancelado = false;
    generarTarjetaQR(visita)
      .then(blob => {
        if (cancelado || !blob) { if (!blob) setError(true); return; }
        const objUrl = URL.createObjectURL(blob);
        urlRef.current = objUrl;
        setUrl(objUrl);
      })
      .catch(() => !cancelado && setError(true));

    return () => {
      cancelado = true;
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    };
  }, [visita.id, visita.qr_token]);

  if (error) return <div className="muted small">No se pudo generar el código QR.</div>;
  if (!url) return <div className="qr-skeleton" />;
  return <img className={className} src={url} alt="Código QR de acceso" />;
}

/** Descarga la tarjeta como PNG (para el botón "Compartir"/"Descargar"). */
export async function descargarTarjetaQR(visita: VisitaDTO) {
  const blob = await generarTarjetaQR(visita);
  if (!blob) return;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `qr_${visita.nombre_visitante.replace(/\s+/g, "_")}.png`;
  a.click();
  URL.revokeObjectURL(url);
}
