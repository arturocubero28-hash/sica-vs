/**
 * Cliente HTTP central de SICA-VS.
 *
 * Patrón para TODO el equipo:
 *   - Todas las llamadas a la API pasan por aquí.
 *   - El token JWT se adjunta automáticamente.
 *   - Cada módulo agrega sus funciones tipadas (ver ejemplos al final).
 */

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:5000/api/v1";

// ---- Tipos compartidos (cada módulo amplía los suyos en src/api) ----
export type Rol = "super_admin" | "admin" | "guardia" | "residente";

export interface Usuario {
  id: string;
  nombre: string;
  apellido: string;
  email: string;
  telefono?: string;
  rol: Rol;
  activo: boolean;
  biometria_activa: boolean;
}

interface ApiError {
  error: { code: string; message: string };
}

// ---- Manejo del token (en memoria + localStorage) ----
const TOKEN_KEY = "sicavs_token";
export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t: string) => localStorage.setItem(TOKEN_KEY, t);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

// ---- Función base de fetch con token y manejo de errores ----
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_URL}${path}`, { ...options, headers });
  const json = await res.json();

  if (!res.ok) {
    const err = json as ApiError;
    throw new Error(err.error?.message || "Error de servidor");
  }
  return (json as { data: T }).data;
}

// =====================================================================
// AUTENTICACIÓN (Integrante 1)
// =====================================================================
export async function login(email: string, password: string) {
  const data = await request<{ token: string; usuario: Usuario }>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  setToken(data.token);
  return data.usuario;
}

export async function getMe() {
  const data = await request<{ usuario: Usuario }>("/auth/me");
  return data.usuario;
}

export function logout() {
  clearToken();
}

// =====================================================================
// EJEMPLOS PARA OTROS MÓDULOS (descomentar y completar cada dueño)
// =====================================================================
//
// export interface Cuenta { id: string; identificador: string; estado: string; }
// export const listarCuentas = () => request<Cuenta[]>("/cuentas");
// export const crearVisita = (datos: NuevaVisita) =>
//   request<Visita>("/visitas", { method: "POST", body: JSON.stringify(datos) });

// =====================================================================
// MÓDULO 2 — Unidades, Cuentas, Residentes, Tarjetas (Integrante 2)
// =====================================================================
export interface Tarifa { id: number; nombre: string; monto: number; }
export interface Unidad {
  id: string; tipo: "casa" | "edificio"; identificador: string;
  direccion_ref?: string; activa: boolean; total_cuentas: number;
}
export interface ResidenteDTO {
  id: string; rol_cuenta: "titular" | "miembro"; relacion?: string;
  nombre: string; email: string; estado_acceso: "activo" | "pendiente";
}
export interface TarjetaDTO {
  id: string; card_uid: string; etiqueta?: string; estado: string; asignada_a: string;
}
export interface Cuenta {
  id: string; apartamento?: string; dia_pago: number; estado: string;
  bloqueada: boolean; tarifa: string; monto: number;
  titular?: ResidenteDTO; total_residentes: number; total_tarjetas: number;
  residentes?: ResidenteDTO[]; tarjetas?: TarjetaDTO[];
}

export const listarUnidades = () => request<Unidad[]>("/unidades");
export const listarCuentas = () => request<Cuenta[]>("/unidades/cuentas");
export const listarTarifas = () => request<Tarifa[]>("/unidades/tarifas");
export const detalleCuenta = (id: string) => request<Cuenta>(`/unidades/cuentas/${id}`);

export const crearUnidad = (body: { tipo: string; identificador: string; direccion_ref?: string }) =>
  request<Unidad>("/unidades", { method: "POST", body: JSON.stringify(body) });

export interface NuevaCuenta {
  unidad_id: string; apartamento?: string; tarifa_id: number; dia_pago: number;
  titular: { nombre: string; apellido: string; email: string; telefono?: string; relacion?: string };
}
export const crearCuenta = (body: NuevaCuenta) =>
  request<{ cuenta: Cuenta; activacion: { usuario_email: string; token_activacion: string } }>(
    "/unidades/cuentas", { method: "POST", body: JSON.stringify(body) });

export const agregarMiembro = (cuentaId: string, body: object) =>
  request<{ residente: ResidenteDTO }>(`/unidades/cuentas/${cuentaId}/residentes`,
    { method: "POST", body: JSON.stringify(body) });

export const asignarTarjeta = (cuentaId: string, body: { card_uid: string; etiqueta?: string; residente_id?: string }) =>
  request<TarjetaDTO>(`/unidades/cuentas/${cuentaId}/tarjetas`,
    { method: "POST", body: JSON.stringify(body) });

// =====================================================================
// AUTH: Activación y Recuperación de contraseña
// =====================================================================
export const activarCuenta = (token: string, password: string) =>
  request<{ message: string; token: string; usuario: Usuario }>("/auth/activar",
    { method: "POST", body: JSON.stringify({ token, password }) });

export const solicitarRecuperacion = (email: string) =>
  request<{ message: string; dev_token?: string }>("/auth/recuperar",
    { method: "POST", body: JSON.stringify({ email }) });

export const restablecerPassword = (token: string, password: string) =>
  request<{ message: string }>("/auth/reset",
    { method: "POST", body: JSON.stringify({ token, password }) });

// =====================================================================
// MÓDULO 3 — Visitas (Residente + Guardia)
// =====================================================================
export interface VisitaDTO {
  id: string; tipo: "unica" | "recurrente" | "repartidor";
  nombre_visitante: string; documento_id?: string; telefono?: string;
  empresa?: string; placa_vehiculo?: string; en_vehiculo: boolean;
  valido_desde?: string; valido_hasta?: string; modo_recurrencia?: string;
  estado: string; qr_token?: string; generada_por?: string; created_at?: string;
}

export interface MiCuentaDTO { cuenta: Cuenta; residente: ResidenteDTO; }

export const miCuenta = () => request<MiCuentaDTO>("/visitas/mi-cuenta");
export const misVisitas = () => request<VisitaDTO[]>("/visitas/mias");

export const crearVisita = (body: {
  tipo: string; nombre_visitante: string; documento_id?: string;
  telefono?: string; empresa?: string; placa_vehiculo?: string;
  en_vehiculo?: boolean; valido_hasta?: string; modo_recurrencia?: string;
}) => request<VisitaDTO>("/visitas", { method: "POST", body: JSON.stringify(body) });

export const validarQR = (token: string) =>
  request<{ visita: VisitaDTO; valido: boolean; mensaje: string }>(
    "/visitas/qr/validar", { method: "POST", body: JSON.stringify({ token }) });

export const registrarAcceso = (body: {
  visita_id: string; direccion: string; acceso_id?: number;
  foto_identidad?: string; foto_placa?: string;
}) => request<{ evento: object; mensaje: string }>(
    "/visitas/accesos/visita", { method: "POST", body: JSON.stringify(body) });

// URL de la imagen QR (con token en query para autenticación de imagen)
export function urlImagenQR(visitaId: string): string {
  const token = getToken();
  return `${API_URL}/visitas/${visitaId}/qr-imagen?_auth=${token}`;
}

// Obtiene la imagen QR como blob (para descargar/compartir)
export async function obtenerImagenQR(visitaId: string): Promise<Blob> {
  const res = await fetch(`${API_URL}/visitas/${visitaId}/qr-imagen`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!res.ok) throw new Error("No se pudo generar la imagen");
  return res.blob();
}
