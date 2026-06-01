import { useState, useEffect } from "react";
import { listarComunicados, urlImagenComunicado, type ComunicadoDTO } from "../../api/client";

export function HomeResidente() {
  const [comunicados, setComunicados] = useState<ComunicadoDTO[]>([]);
  const [cargando, setCargando] = useState(true);

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
          <div className="cuota-vacia-icon">📣</div>
          <p>No hay comunicados por ahora.</p>
          <p className="muted small">Aquí verás los anuncios de la administración.</p>
        </div>
      ) : (
        <div className="comunicado-feed">
          {comunicados.map(c => <ComunicadoCard key={c.id} com={c} />)}
        </div>
      )}
    </div>
  );
}

function ComunicadoCard({ com }: { com: ComunicadoDTO }) {
  const [abierto, setAbierto] = useState(false);
  const esLargo = com.cuerpo.length > 180;
  const fecha = new Date(com.created_at).toLocaleDateString("es-HN", {
    day: "numeric", month: "long", year: "numeric",
  });

  return (
    <div className={`comunicado-card ${abierto ? "abierto" : ""}`} onClick={() => esLargo && setAbierto(!abierto)}>
      {com.imagen && (
        <div className="comunicado-img-wrap">
          <img src={urlImagenComunicado(com.imagen)} alt={com.titulo} />
        </div>
      )}
      <div className="comunicado-contenido">
        <div className="comunicado-fecha">{fecha}</div>
        <h3 className="comunicado-titulo">{com.titulo}</h3>
        <p className={`comunicado-cuerpo ${!abierto && esLargo ? "truncado" : ""}`}>
          {com.cuerpo}
        </p>
        {esLargo && (
          <button className="comunicado-toggle" onClick={(e) => { e.stopPropagation(); setAbierto(!abierto); }}>
            {abierto ? "Ver menos" : "Leer más"}
          </button>
        )}
        <div className="comunicado-autor muted small">Publicado por {com.autor}</div>
      </div>
    </div>
  );
}
