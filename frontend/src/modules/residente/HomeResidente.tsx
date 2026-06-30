import { useState, useEffect } from "react";
import { listarComunicados, urlImagenComunicado, type ComunicadoDTO } from "../../api/client";
import { Megaphone } from "lucide-react";

export function HomeResidente() {
  const [comunicados, setComunicados] = useState<ComunicadoDTO[]>([]);
  const [cargando, setCargando] = useState(true);
  const [abierto, setAbierto] = useState<ComunicadoDTO | null>(null);

  useEffect(() => {
    listarComunicados().then(setComunicados).catch(() => {}).finally(() => setCargando(false));
  }, []);

  if (cargando) return <p className="muted">Cargando comunicados…</p>;

  return (
    <div className="home-residente">
      <div className="home-saludo">
        <h2>Comunidad Villas del Sol</h2>
        <p className="muted">Anuncios y comunicados de la administración</p>
      </div>

      {comunicados.length === 0 ? (
        <div className="cuota-vacia">
          <div className="cuota-vacia-icon"><Megaphone size={16} /></div>
          <p>No hay comunicados por ahora.</p>
          <p className="muted small">Aquí verás los anuncios de la administración.</p>
        </div>
      ) : (
        <div className="comunicado-feed">
          {comunicados.map(c => (
            <ComunicadoMini key={c.id} com={c} onAbrir={() => setAbierto(c)} />
          ))}
        </div>
      )}

      {abierto && <ComunicadoModal com={abierto} onCerrar={() => setAbierto(null)} />}
    </div>
  );
}

// Card compacta: solo título, fecha y foto pequeña
function ComunicadoMini({ com, onAbrir }: { com: ComunicadoDTO; onAbrir: () => void }) {
  const fecha = new Date(com.created_at).toLocaleDateString("es-HN", {
    day: "numeric", month: "long", year: "numeric",
  });
  return (
    <div className="comunicado-mini" onClick={onAbrir}>
      {com.imagen && (
        <img className="comunicado-mini-foto" src={urlImagenComunicado(com.imagen)} alt="" />
      )}
      <div className="comunicado-mini-texto">
        <div className="comunicado-fecha">{fecha}</div>
        <h3 className="comunicado-mini-titulo">{com.titulo}</h3>
      </div>
      <span className="comunicado-mini-chevron">›</span>
    </div>
  );
}

// Modal con el comunicado completo
function ComunicadoModal({ com, onCerrar }: { com: ComunicadoDTO; onCerrar: () => void }) {
  const fecha = new Date(com.created_at).toLocaleDateString("es-HN", {
    day: "numeric", month: "long", year: "numeric",
  });
  return (
    <div className="modal" onClick={onCerrar}>
      <div className="modal-body" onClick={e => e.stopPropagation()}>
        <div className="modal-head">
          <h3>{com.titulo}</h3>
          <button className="ghost mini" onClick={onCerrar}>✕</button>
        </div>
        <div className="comunicado-fecha" style={{ marginBottom: 12 }}>{fecha}</div>
        {com.imagen && (
          <div className="comunicado-modal-img">
            <img src={urlImagenComunicado(com.imagen)} alt={com.titulo} />
          </div>
        )}
        <p className="comunicado-modal-cuerpo">{com.cuerpo}</p>
        <div className="comunicado-autor muted small">Publicado por {com.autor}</div>
      </div>
    </div>
  );
}
