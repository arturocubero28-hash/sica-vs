/**
 * Cliente HTTP central de SICA-VS.
 *
 * Patrón para TODO el equipo:
 *   - Todas las llamadas a la API pasan por aquí.
 *   - El token JWT se adjunta automáticamente.
 *   - Cada módulo agrega sus funciones tipadas (ver ejemplos al final).
 */

const API_URL = "/api/v1";

// ---- Tipos compartidos (cada módulo amplía los suyos en src/api) ----
export type Rol = "super_admin" | "admin" | "guardia" | "residente" | "cajero" | "desarrollador";

export interface Usuario {
  id: string;
  nombre: string;
  apellido: string;
  email: string;
  telefono?: string;
  rol: Rol;
  activo: boolean;
  debe_cambiar_password?: boolean;
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
  id: string; apartamento?: string; identificador?: string; dia_pago: number; estado: string;
  bloqueada: boolean; activa?: boolean; tarifa: string; monto: number;
  titular?: ResidenteDTO; total_residentes: number; total_tarjetas: number;
  residentes?: ResidenteDTO[]; tarjetas?: TarjetaDTO[];
}

export const listarUnidades = () => request<Unidad[]>("/unidades");
export const listarCuentas = () => request<Cuenta[]>("/unidades/cuentas");
export const listarTarifas = () => request<Tarifa[]>("/unidades/tarifas");
export const detalleCuenta = (id: string) => request<Cuenta>(`/unidades/cuentas/${id}`);
export const darBajaCuenta = (id: string) =>
  request<Cuenta>(`/unidades/cuentas/${id}/baja`, { method: "POST" });
export const reactivarCuenta = (id: string) =>
  request<Cuenta>(`/unidades/cuentas/${id}/reactivar`, { method: "POST" });

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

export const cancelarVisita = (visitaId: string) =>
  request<VisitaDTO>(`/visitas/${visitaId}/cancelar`, { method: "POST" });

export const validarQR = (token: string) =>
  request<{
    visita: VisitaDTO; valido: boolean; mensaje: string;
    adentro?: boolean; direccion_sugerida?: "entrada" | "salida";
  }>(
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

// =====================================================================
// Dashboard administrativo
// =====================================================================
export interface MetricasDTO {
  qr_generados_hoy: number; visitantes_activos: number;
  qr_utilizados: number; qr_expirados: number;
  total_unidades: number; total_cuentas: number;
  total_residentes: number; cuentas_bloqueadas: number; accesos_hoy: number;
  adentro_ahora: number;
}
export interface VisitaTablaDTO {
  id: string; residente: string; unidad: string; visitante: string;
  tipo: string; estado: string; vigencia: string; creado: string;
}
export interface VisitaActivaDTO {
  id: string;
  visitante: string; tipo: string; empresa?: string;
  documento_id?: string; telefono?: string;
  en_vehiculo: boolean; placa?: string;
  residente: string; unidad: string;
  guardia_autorizo?: string;
  hora_creacion?: string; hora_entrada?: string; hora_salida?: string;
  foto_identidad?: string; foto_placa?: string;
}
export const dashboardMetricas = () => request<MetricasDTO>("/dashboard/metricas");
export const dashboardVisitas = () => request<VisitaTablaDTO[]>("/dashboard/visitas-tabla");
export const dashboardVisitasActivas = () => request<VisitaActivaDTO[]>("/dashboard/visitas-activas");

// URL de una foto tomada por el guardia (con token para autenticación)
export function urlFotoGuardia(nombreArchivo: string): string {
  const token = getToken();
  return `${API_URL}/dashboard/fotos/${nombreArchivo}?_auth=${token}`;
}

// ── CUOTAS Y PAGOS ────────────────────────────────────────────────────────────
export interface CuotaDTO {
  id: string; periodo: string; mes_label: string;
  monto: number; fecha_vencimiento: string; estado: string;
  created_at: string; pagos?: PagoDTO[];
  pago_rechazado?: boolean; nota_rechazo?: string;
}
export interface PagoDTO {
  id: string; cuota_id: string; monto: number; metodo: string;
  referencia?: string; comprobante_archivo?: string;
  estado: string; nota_admin?: string; revisado_en?: string; created_at: string;
}
export interface PagoAdminDTO extends PagoDTO {
  unidad: string; periodo: string; mes_label: string;
}

export const misCuotas = () => request<CuotaDTO[]>("/cuotas/mias");
export const detalleCuota = (uuid: string) => request<CuotaDTO>(`/cuotas/mias/${uuid}`);

export async function subirComprobante(
  cuotaUuid: string, archivo: File, monto: number, referencia: string
): Promise<PagoDTO> {
  const token = getToken();
  const form = new FormData();
  form.append("comprobante", archivo);
  form.append("monto", String(monto));
  form.append("referencia", referencia);
  const res = await fetch(`${API_URL}/cuotas/mias/${cuotaUuid}/pagar`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  const json = await res.json();
  if (!res.ok) throw new Error(json.error?.message || "Error al subir comprobante");
  return json.data;
}

export const cuotasPendientesAdmin = () => request<PagoAdminDTO[]>("/cuotas/pendientes");
export const revisarPago = (uuid: string, accion: "aprobar" | "rechazar", nota?: string) =>
  request<PagoDTO>(`/cuotas/pagos/${uuid}/revisar`, {
    method: "POST",
    body: JSON.stringify({ accion, nota: nota || "" }),
  });

// ── CÁMARAS ───────────────────────────────────────────────────────────────────
export interface CamaraDTO {
  id: string; nombre: string; ip: string;
  puerto_rtsp: number; puerto_onvif: number;
  usuario?: string; ruta_stream?: string;
  acceso_id?: number; activa: boolean; orden: number;
}
export const listarCamaras = () => request<CamaraDTO[]>("/camaras");
export const crearCamara = (body: Partial<CamaraDTO> & { password?: string }) =>
  request<CamaraDTO>("/camaras", { method: "POST", body: JSON.stringify(body) });
export const editarCamara = (uuid: string, body: Partial<CamaraDTO> & { password?: string }) =>
  request<CamaraDTO>(`/camaras/${uuid}`, { method: "PUT", body: JSON.stringify(body) });
export const eliminarCamara = (uuid: string) =>
  request<{ eliminada: boolean }>(`/camaras/${uuid}`, { method: "DELETE" });
export const probarCamara = (uuid: string) =>
  request<{ online: boolean; error?: string }>(`/camaras/${uuid}/probar`, { method: "POST" });

// URL del stream MJPEG (con token para autenticación en el <img>)
export function urlStreamCamara(uuid: string): string {
  const token = getToken();
  return `${API_URL}/camaras/${uuid}/stream?_auth=${token}`;
}

// ── COMUNICADOS ───────────────────────────────────────────────────────────────
export interface ComunicadoDTO {
  id: string; titulo: string; cuerpo: string;
  imagen?: string; autor: string; created_at: string;
}
export const listarComunicados = () => request<ComunicadoDTO[]>("/comunicados");
export const eliminarComunicado = (uuid: string) =>
  request<{ eliminado: boolean }>(`/comunicados/${uuid}`, { method: "DELETE" });

export async function crearComunicado(
  titulo: string, cuerpo: string, imagen?: File | null
): Promise<ComunicadoDTO> {
  const token = getToken();
  const form = new FormData();
  form.append("titulo", titulo);
  form.append("cuerpo", cuerpo);
  if (imagen) form.append("imagen", imagen);
  const res = await fetch(`${API_URL}/comunicados`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  const json = await res.json();
  if (!res.ok) throw new Error(json.error?.message || "Error al crear comunicado");
  return json.data;
}

export function urlImagenComunicado(nombre: string): string {
  const token = getToken();
  return `${API_URL}/comunicados/imagenes/${nombre}?_auth=${token}`;
}

export const generarCuotasManual = () =>
  request<{ generadas: number; total_cuentas: number }>("/cuotas/generar", { method: "POST" });

export function urlComprobante(nombre: string): string {
  const token = getToken();
  return `${API_URL}/cuotas/comprobantes/${nombre}?_auth=${token}`;
}

// ── REPORTES ──────────────────────────────────────────────────────────────────
export interface MorosoDTO {
  unidad: string; titular: string; monto: number;
  estado: string; vencimiento: string; dias_atraso: number;
}
export interface AlDiaDTO { unidad: string; titular: string; monto: number; }
export interface TendenciaDTO { mes_label: string; esperado: number; recaudado: number; }
export interface ReporteFinancieroDTO {
  periodo: string; mes_label: string;
  total_esperado: number; total_recaudado: number; total_pendiente: number;
  pct_cobranza: number; cuentas_al_dia: number; cuentas_morosas: number;
  al_dia: AlDiaDTO[]; morosos: MorosoDTO[]; tendencia: TendenciaDTO[];
}
export const reporteFinanciero = (anio?: number, mes?: number) => {
  const q = anio && mes ? `?anio=${anio}&mes=${mes}` : "";
  return request<ReporteFinancieroDTO>(`/reportes/financiero${q}`);
};

// ── PERFIL ────────────────────────────────────────────────────────────────────
export const cambiarPassword = (passwordActual: string, passwordNueva: string) =>
  request<{ message: string; usuario: Usuario }>("/auth/cambiar-password", {
    method: "POST",
    body: JSON.stringify({ password_actual: passwordActual, password_nueva: passwordNueva }),
  });
export const actualizarPerfil = (body: { nombre?: string; apellido?: string; telefono?: string }) =>
  request<{ usuario: Usuario }>("/auth/perfil", { method: "PUT", body: JSON.stringify(body) });

// ── GUARDIAS ──────────────────────────────────────────────────────────────────
export interface GuardiaDTO {
  id: string; nombre: string; apellido: string; email: string;
  rol: string; activo: boolean; debe_cambiar_password?: boolean;
  password_generica?: string;
}
export const listarGuardias = () => request<GuardiaDTO[]>("/guardias");
export const crearGuardia = (body: { nombre: string; apellido: string; email: string }) =>
  request<GuardiaDTO>("/guardias", { method: "POST", body: JSON.stringify(body) });
export const editarGuardia = (uuid: string, body: { nombre?: string; apellido?: string; activo?: boolean }) =>
  request<GuardiaDTO>(`/guardias/${uuid}`, { method: "PUT", body: JSON.stringify(body) });
export const resetPasswordGuardia = (uuid: string) =>
  request<{ message: string; password_generica: string }>(`/guardias/${uuid}/reset-password`, { method: "POST" });

// ── HISTORIAL DE ACCESOS ──────────────────────────────────────────────────────
export interface EventoHistorialDTO {
  id: string; direccion: string; visitante: string;
  unidad: string; guardia: string; placa?: string; ocurrido_en: string;
}
export interface HistorialDTO {
  eventos: EventoHistorialDTO[];
  pagina: number; por_pagina: number; total: number; total_paginas: number;
}
export const historialAccesos = (params: {
  desde?: string; hasta?: string; direccion?: string; buscar?: string; pagina?: number;
}) => {
  const q = new URLSearchParams();
  if (params.desde) q.set("desde", params.desde);
  if (params.hasta) q.set("hasta", params.hasta);
  if (params.direccion) q.set("direccion", params.direccion);
  if (params.buscar) q.set("buscar", params.buscar);
  if (params.pagina) q.set("pagina", String(params.pagina));
  const qs = q.toString();
  return request<HistorialDTO>(`/dashboard/historial${qs ? "?" + qs : ""}`);
};

// ── NOTIFICACIONES ────────────────────────────────────────────────────────────
export const contarPagosPendientes = () =>
  request<{ pendientes: number }>("/cuotas/pendientes/count");

// ── USUARIOS ──────────────────────────────────────────────────────────────────
export interface UsuarioAdminDTO {
  id: string; nombre: string; apellido: string; email: string;
  rol: string; activo: boolean; debe_cambiar_password?: boolean;
  password_generica?: string;
}
export const listarUsuarios = (params?: { rol?: string; buscar?: string }) => {
  const q = new URLSearchParams();
  if (params?.rol) q.set("rol", params.rol);
  if (params?.buscar) q.set("buscar", params.buscar);
  const qs = q.toString();
  return request<UsuarioAdminDTO[]>(`/usuarios${qs ? "?" + qs : ""}`);
};
export const crearCajero = (body: { nombre: string; apellido: string; email: string }) =>
  request<UsuarioAdminDTO>("/usuarios/cajeros", { method: "POST", body: JSON.stringify(body) });
export const resetPasswordUsuario = (uuid: string) =>
  request<{ message: string; password_generica: string }>(`/usuarios/${uuid}/reset-password`, { method: "POST" });
export const editarUsuario = (uuid: string, body: { activo?: boolean }) =>
  request<UsuarioAdminDTO>(`/usuarios/${uuid}`, { method: "PUT", body: JSON.stringify(body) });

// ── CAJA ──────────────────────────────────────────────────────────────────────
export interface CuotaPendienteCaja { cuota_id: string; mes_label: string; monto: number; estado: string; }
export interface CuentaCajaDTO {
  cuenta_id: string; identificador: string; titular: string;
  cuotas_pendientes: CuotaPendienteCaja[];
}
export interface SesionCajaDTO {
  id: string; estado: string; cajero: string; monto_inicial: number;
  total_efectivo: number; total_pos: number; total_otros: number;
  total_salidas?: number;
  cantidad_pagos: number; efectivo_esperado: number; pos_esperado: number;
  abierta_en: string; cerrada_en?: string;
  efectivo_contado?: number; pos_contado?: number;
  diferencia_efectivo?: number; diferencia_pos?: number; nota_cierre?: string;
  pagos?: { id: string; monto: number; metodo: string; referencia?: string; hora: string }[];
}
export const estadoCaja = () => request<{ abierta: boolean; sesion?: SesionCajaDTO }>("/caja/estado");
export const abrirCaja = (montoInicial: number) =>
  request<SesionCajaDTO>("/caja/abrir", { method: "POST", body: JSON.stringify({ monto_inicial: montoInicial }) });
export const buscarCuentaCaja = (q: string) =>
  request<CuentaCajaDTO[]>(`/caja/buscar-cuenta?q=${encodeURIComponent(q)}`);
export const registrarPagoCaja = (body: { cuota_id: string; metodo: string; referencia?: string }) =>
  request<{ pago: any; sesion: SesionCajaDTO }>("/caja/pago", { method: "POST", body: JSON.stringify(body) });
export const cerrarCaja = (body: { efectivo_contado: number; pos_contado: number; nota?: string }) =>
  request<SesionCajaDTO>("/caja/cerrar", { method: "POST", body: JSON.stringify(body) });
export const listarSesionesCaja = () => request<SesionCajaDTO[]>("/caja/sesiones");
export const detalleSesionCaja = (uuid: string) => request<SesionCajaDTO>(`/caja/sesiones/${uuid}`);

// ── RESUMEN DE CAJA (saldo del sistema) ───────────────────────────────────────
export interface ResumenCajaDTO {
  saldo_inicial: number; saldo_actual: number;
  total_efectivo_historico: number; total_pos_historico: number;
  total_salidas_historico?: number;
  total_ajustes?: number;
  efectivo_en_cajas_abiertas: number; cajas_abiertas: number;
  descuadres_pendientes?: number;
  actualizado_en?: string;
}
export const resumenCaja = () => request<ResumenCajaDTO>("/caja/resumen");

// ── PANEL DESARROLLADOR ───────────────────────────────────────────────────────
export interface DevMetricasDTO {
  estado_general: string; timestamp: string;
  db_conectada: boolean; db_latencia_ms?: number; db_error?: string;
  redis?: { conectado: boolean; error?: string };
  sistema?: {
    error?: string;
    disco?: { total_gb: number; usado_gb: number; libre_gb: number; porcentaje: number };
    ram?:   { total_gb: number; usado_gb: number; libre_gb: number; porcentaje: number };
    cpu_porcentaje?: number;
  };
  errores_recientes?: any[];
}
export const devMetricas = () => request<DevMetricasDTO>("/dev/metricas");
export const devLogs = (params?: { email?: string; endpoint?: string; errores?: string; pagina?: number }) => {
  const q = new URLSearchParams();
  if (params?.email) q.set("email", params.email);
  if (params?.endpoint) q.set("endpoint", params.endpoint);
  if (params?.errores) q.set("errores", params.errores);
  if (params?.pagina) q.set("pagina", String(params.pagina));
  return request<any>(`/dev/logs?${q.toString()}`);
};
export const crearDesarrollador = (body: { nombre: string; apellido: string; email: string }) =>
  request<UsuarioAdminDTO>("/usuarios/desarrolladores", { method: "POST", body: JSON.stringify(body) });

// ── SALDO INICIAL Y DESCUADRES ────────────────────────────────────────────────
export const modificarSaldoInicial = (saldoInicial: number, claveDev: string) =>
  request<{ saldo_inicial: number }>("/caja/saldo-inicial", {
    method: "POST", body: JSON.stringify({ saldo_inicial: saldoInicial, clave_dev: claveDev }),
  });

export interface DescuadreDTO {
  id: string; tipo: string; monto: number; motivo?: string; estado: string;
  reportado_por: string; aprobado_por?: string; created_at: string; resuelto_en?: string;
}
export const reportarDescuadre = (body: { tipo: string; monto: number; motivo?: string }) =>
  request<DescuadreDTO>("/caja/descuadre", { method: "POST", body: JSON.stringify(body) });
export const listarDescuadres = (estado?: string) =>
  request<DescuadreDTO[]>(`/caja/descuadres${estado ? "?estado=" + estado : ""}`);
export const resolverDescuadre = (uuid: string, accion: string, claveDev?: string) =>
  request<DescuadreDTO>(`/caja/descuadres/${uuid}/resolver`, {
    method: "POST", body: JSON.stringify({ accion, clave_dev: claveDev }),
  });

// ── HISTORIAL DE PAGOS (auditoría admin) ──────────────────────────────────────
export interface PagoHistorialItem {
  id: string; fecha: string; monto: number; metodo: string; referencia?: string;
  identificador: string; titular: string; cobrado_por: string;
}
export interface HistorialPagosDTO {
  pagos: PagoHistorialItem[]; pagina: number; total_paginas: number; total: number;
}
export const historialPagos = (params: {
  desde?: string; hasta?: string; metodo?: string; buscar?: string; pagina?: number;
}) => {
  const q = new URLSearchParams();
  if (params.desde) q.set("desde", params.desde);
  if (params.hasta) q.set("hasta", params.hasta);
  if (params.metodo) q.set("metodo", params.metodo);
  if (params.buscar) q.set("buscar", params.buscar);
  if (params.pagina) q.set("pagina", String(params.pagina));
  return request<HistorialPagosDTO>(`/cuotas/historial-pagos?${q.toString()}`);
};

// ── SALIDAS DE CAJA ───────────────────────────────────────────────────────────
export interface SalidaCajaDTO {
  id: string; sesion_id?: string; monto: number; concepto: string; estado: string;
  solicitado_por: string; autorizado_por?: string; created_at: string; resuelto_en?: string;
}
export const solicitarSalida = (body: { monto: number; concepto: string }) =>
  request<SalidaCajaDTO>("/caja/salida", { method: "POST", body: JSON.stringify(body) });
export const listarSalidas = (estado?: string) =>
  request<SalidaCajaDTO[]>(`/caja/salidas${estado ? "?estado=" + estado : ""}`);
export const autorizarSalida = (uuid: string, accion: string, clave?: string) =>
  request<SalidaCajaDTO>(`/caja/salidas/${uuid}/autorizar`, {
    method: "POST", body: JSON.stringify({ accion, clave }),
  });
export const salidasPendientes = () => request<SalidaCajaDTO[]>("/caja/salidas/pendientes");

export const solicitarIngreso = (body: { monto: number; concepto: string }) =>
  request<SalidaCajaDTO>("/caja/ingreso", { method: "POST", body: JSON.stringify(body) });
