/**
 * Gráficos reutilizables para la reportería, con la paleta de SICA-VS.
 * Usa Recharts. Cada componente recibe datos ya formateados y se encarga
 * solo de la presentación.
 */
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  LineChart, Line, PieChart, Pie, Cell,
} from "recharts";

// Paleta de marca
const NARANJA = "#F48723";
const AZUL = "#022E45";
const AZUL2 = "#044a6e";
const VERDE = "#1d8a4a";
const ROJO = "#c81e1e";
const AMBER = "#d89000";
const GRIS = "#9ca3af";

const PALETA = [AZUL, NARANJA, VERDE, AMBER, AZUL2, ROJO];

// Formato corto de Lempiras para los ejes (L 1.2k, L 3.4M)
function fmtCorto(n: number): string {
  if (n >= 1_000_000) return `L ${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `L ${(n / 1_000).toFixed(1)}k`;
  return `L ${n}`;
}

function fmtLps(n: number): string {
  return new Intl.NumberFormat("es-HN", { style: "currency", currency: "HNL", maximumFractionDigits: 0 }).format(n);
}

const cajaTooltip = {
  contentStyle: { borderRadius: 10, border: "1px solid #e3e9f2", fontSize: 13 },
};

/** Barras comparativas (ej. esperado vs recaudado vs pendiente). */
export function GraficoBarras({ titulo, datos }: {
  titulo?: string;
  datos: { nombre: string; valor: number; color?: string }[];
}) {
  return (
    <div className="grafico-card">
      {titulo && <h4 className="grafico-titulo">{titulo}</h4>}
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={datos} margin={{ top: 8, right: 12, left: 4, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" vertical={false} />
          <XAxis dataKey="nombre" tick={{ fontSize: 12, fill: "#6b7280" }} />
          <YAxis tickFormatter={fmtCorto} tick={{ fontSize: 11, fill: "#9ca3af" }} width={64} />
          <Tooltip formatter={(v: number) => fmtLps(v)} {...cajaTooltip} />
          <Bar dataKey="valor" radius={[6, 6, 0, 0]}>
            {datos.map((d, i) => <Cell key={i} fill={d.color || PALETA[i % PALETA.length]} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Dona para composición (ej. recaudado por método, tipos de visita). */
export function GraficoDona({ titulo, datos, money = true }: {
  titulo?: string;
  datos: { nombre: string; valor: number }[];
  money?: boolean;
}) {
  const total = datos.reduce((s, d) => s + d.valor, 0);
  if (total === 0) {
    return (
      <div className="grafico-card">
        {titulo && <h4 className="grafico-titulo">{titulo}</h4>}
        <p className="muted" style={{ textAlign: "center", padding: "40px 0" }}>Sin datos en el período</p>
      </div>
    );
  }
  return (
    <div className="grafico-card">
      {titulo && <h4 className="grafico-titulo">{titulo}</h4>}
      <ResponsiveContainer width="100%" height={240}>
        <PieChart>
          <Pie data={datos} dataKey="valor" nameKey="nombre" cx="50%" cy="50%"
            innerRadius={55} outerRadius={85} paddingAngle={2}>
            {datos.map((_, i) => <Cell key={i} fill={PALETA[i % PALETA.length]} />)}
          </Pie>
          <Tooltip formatter={(v: number) => money ? fmtLps(v) : String(v)} {...cajaTooltip} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Línea de tendencia (ej. esperado vs recaudado mes a mes). */
export function GraficoLinea({ titulo, datos }: {
  titulo?: string;
  datos: { nombre: string; esperado?: number; recaudado: number }[];
}) {
  const tieneEsperado = datos.some(d => typeof d.esperado === "number");
  return (
    <div className="grafico-card">
      {titulo && <h4 className="grafico-titulo">{titulo}</h4>}
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={datos} margin={{ top: 8, right: 12, left: 4, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" vertical={false} />
          <XAxis dataKey="nombre" tick={{ fontSize: 12, fill: "#6b7280" }} />
          <YAxis tickFormatter={fmtCorto} tick={{ fontSize: 11, fill: "#9ca3af" }} width={64} />
          <Tooltip formatter={(v: number) => fmtLps(v)} {...cajaTooltip} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {tieneEsperado && <Line type="monotone" dataKey="esperado" name="Esperado" stroke={GRIS} strokeWidth={2} dot={{ r: 3 }} strokeDasharray="5 4" />}
          <Line type="monotone" dataKey="recaudado" name="Recaudado" stroke={VERDE} strokeWidth={2.5} dot={{ r: 3 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Barras horizontales para rankings (ej. top deudores), con nombres largos. */
export function GraficoBarrasHoriz({ titulo, datos }: {
  titulo?: string;
  datos: { nombre: string; valor: number }[];
}) {
  return (
    <div className="grafico-card">
      {titulo && <h4 className="grafico-titulo">{titulo}</h4>}
      <ResponsiveContainer width="100%" height={Math.max(220, datos.length * 36)}>
        <BarChart data={datos} layout="vertical" margin={{ top: 4, right: 16, left: 4, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" horizontal={false} />
          <XAxis type="number" tickFormatter={fmtCorto} tick={{ fontSize: 11, fill: "#9ca3af" }} />
          <YAxis type="category" dataKey="nombre" width={150} tick={{ fontSize: 11, fill: "#6b7280" }} />
          <Tooltip formatter={(v: number) => fmtLps(v)} {...cajaTooltip} />
          <Bar dataKey="valor" fill="#c81e1e" radius={[0, 6, 6, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function GraficoBarrasCant({ titulo, datos, color = AZUL }: {
  titulo?: string;
  datos: { nombre: string; valor: number }[];
  color?: string;
}) {
  return (
    <div className="grafico-card">
      {titulo && <h4 className="grafico-titulo">{titulo}</h4>}
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={datos} margin={{ top: 8, right: 12, left: 4, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" vertical={false} />
          <XAxis dataKey="nombre" tick={{ fontSize: 11, fill: "#6b7280" }} />
          <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "#9ca3af" }} width={36} />
          <Tooltip {...cajaTooltip} />
          <Bar dataKey="valor" fill={color} radius={[6, 6, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
