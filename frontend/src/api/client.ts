/**
 * Cliente HTTP central de SICA-VS.
 *
 * Patrón para TODO el equipo:
 *   - Todas las llamadas a la API pasan por aquí.
 *   - El token JWT se adjunta automáticamente.
 *   - Cada módulo agrega sus funciones tipadas (ver ejemplos al final).
 */

import { startRegistration, startAuthentication } from "@simplewebauthn/browser";

const API_URL = "/api/v1";

// ---- Tipos compartidos (cada módulo amplía los suyos en src/api) ----
export type Rol = "super_admin" | "admin" | "supervisor" | "guardia" | "residente" | "cajero" | "desarrollador";

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
const clearToken = () => localStorage.removeItem(TOKEN_KEY);

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

export async function logout() {
  // Avisar al backend para revocar el token (blacklist). Tolerante a fallos:
  // si no responde, igual se borra la sesión local.
  try {
    const token = getToken();
    if (token) {
      await fetch(`${API_URL}/auth/logout`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
      });
    }
  } catch { /* ignorar: igual cerramos sesión localmente */ }
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
export interface Tarifa { id: number; nombre: string; monto: number; descripcion?: string | null; activa?: boolean; }
export interface Unidad {
  id: string; tipo: "casa" | "edificio"; identificador: string;
  direccion_ref?: string; activa: boolean; total_cuentas: number;
}
export interface ResidenteDTO {
  id: string; usuario_id?: string; rol_cuenta: "titular" | "miembro"; relacion?: string;
  nombre: string; nombre_solo?: string; apellido?: string; email: string;
  telefono?: string; dni?: string; rtn?: string; direccion_exacta?: string; profesion?: string;
  contacto_emergencia_nombre?: string; contacto_emergencia_telefono?: string;
  estado_acceso: "activo" | "pendiente";
}
export interface TarjetaDTO {
  id: string; card_uid: string; etiqueta?: string; estado: string; asignada_a: string;
  tipo_acceso?: "vehicular" | "peatonal";
}
export interface CuotaResumen {
  periodo: string; monto: number; estado: string; fecha_vencimiento: string;
}
export interface UnidadDetalle {
  id: string; tipo: "casa" | "edificio"; identificador: string;
  max_apartamentos?: number | null; max_residentes_extra?: number | null; total_cuentas: number;
}
export interface ApartamentoResumen {
  id: string; apartamento?: string; titular: string; estado: string;
  bloqueada: boolean; tarifa?: string | null; monto?: number | null;
}
export interface Cuenta {
  id: string; apartamento?: string; identificador?: string; nombre_completo?: string;
  es_apartamento?: boolean; es_contenedor?: boolean; administra_edificio?: boolean;
  tipo_cuenta?: "casa" | "edificio_contenedor" | "edificio_admin" | "apartamento";
  dia_pago: number; estado: string;
  bloqueada: boolean; activa?: boolean; acceso_pausado?: boolean; tarifa: string; monto: number;
  titular?: ResidenteDTO; total_residentes: number; total_tarjetas: number;
  cuotas_pendientes?: number; qr_recurrente_habilitado?: boolean; created_at?: string;
  tipo_acceso_virtual?: "peatonal" | "vehicular";
  residentes?: ResidenteDTO[]; tarjetas?: TarjetaDTO[];
  unidad?: UnidadDetalle; cuotas_recientes?: CuotaResumen[];
  apartamentos?: ApartamentoResumen[];
}

export const listarUnidades = () => request<Unidad[]>("/unidades");
export const listarCuentas = () => request<Cuenta[]>("/unidades/cuentas");
export const listarTarifas = () => request<Tarifa[]>("/unidades/tarifas");
export const crearTarifa = (body: { nombre: string; monto: number; descripcion?: string }) =>
  request<Tarifa>("/unidades/tarifas", { method: "POST", body: JSON.stringify(body) });
export const editarTarifa = (id: number, body: { nombre?: string; monto?: number; descripcion?: string }) =>
  request<Tarifa>(`/unidades/tarifas/${id}`, { method: "PUT", body: JSON.stringify(body) });
export const desactivarTarifa = (id: number) =>
  request<{ message: string }>(`/unidades/tarifas/${id}`, { method: "DELETE" });

// ── Enrolamiento de inquilinos por código (dueño de edificio) ──
export interface CodigoEnrolamiento {
  id: string; codigo: string; edificio?: string | null;
  apartamento_sugerido?: string | null; nota?: string | null;
  estado: string; created_at?: string; usado_en?: string | null;
}
export const misEdificios = () => request<Unidad[]>("/unidades/mis-edificios");
export const apartamentosDelEdificio = (edificioId: string) =>
  request<Cuenta[]>(`/unidades/mis-edificios/${edificioId}/apartamentos`);
export const crearSolicitudBaja = (body: { cuenta_id: string; motivo: string; fecha_desocupacion: string }) =>
  request<SolicitudBajaDTO>("/unidades/solicitudes-baja", { method: "POST", body: JSON.stringify(body) });
export const generarCodigoEnrolamiento = (body: { edificio_id: string; apartamento?: string; nota?: string }) =>
  request<CodigoEnrolamiento>("/unidades/enrolamiento/generar", { method: "POST", body: JSON.stringify(body) });
export const misCodigosEnrolamiento = () => request<CodigoEnrolamiento[]>("/unidades/enrolamiento/mis-codigos");
export const borrarCodigoEnrolamiento = (id: string) =>
  request<{ message: string }>(`/unidades/enrolamiento/${id}`, { method: "DELETE" });
export interface ValidacionEnrolamiento {
  codigo_id: string; edificio_id: string; edificio_nombre: string;
  apartamento_sugerido?: string | null; nota?: string | null; dueno_nombre?: string | null;
}
export const validarCodigoEnrolamiento = (codigo: string) =>
  request<ValidacionEnrolamiento>(`/unidades/enrolamiento/validar/${codigo}`);
export const detalleCuenta = (id: string) => request<Cuenta>(`/unidades/cuentas/${id}`);
export const darBajaCuenta = (id: string) =>
  request<Cuenta>(`/unidades/cuentas/${id}/baja`, { method: "POST" });
export const reactivarCuenta = (id: string) =>
  request<Cuenta>(`/unidades/cuentas/${id}/reactivar`, { method: "POST" });
// Día 53 — Sprint 1: pausa liviana y reversible, distinta de dar de baja.
export const pausarAcceso = (id: string) =>
  request<Cuenta>(`/unidades/cuentas/${id}/pausar-acceso`, { method: "POST" });
export const reanudarAcceso = (id: string) =>
  request<Cuenta>(`/unidades/cuentas/${id}/reanudar-acceso`, { method: "POST" });

export interface SolicitudBajaDTO {
  id: string; cuenta_id: string; apartamento: string; edificio: string;
  titular: string; solicitada_por: string; motivo: string;
  fecha_desocupacion: string; estado: string; respuesta_admin?: string;
  created_at: string; resuelto_en?: string;
}
export const listarSolicitudesBaja = (estado = "pendiente") =>
  request<SolicitudBajaDTO[]>(`/unidades/solicitudes-baja?estado=${estado}`);
export const resolverSolicitudBaja = (id: string, accion: string, respuesta?: string) =>
  request<SolicitudBajaDTO>(`/unidades/solicitudes-baja/${id}/resolver`,
    { method: "POST", body: JSON.stringify({ accion, respuesta }) });
export const nivelarSaldo = (cuentaId: string, fechaDesocupacion: string) =>
  request<{ message: string; ajustes: { periodo: string; accion: string; dias_ocupados?: number; monto_original: number; monto_final: number }[] }>(
    `/unidades/cuentas/${cuentaId}/nivelar-saldo`,
    { method: "POST", body: JSON.stringify({ fecha_desocupacion: fechaDesocupacion }) });

export const crearUnidad = (body: { tipo: string; identificador: string; direccion_ref?: string }) =>
  request<Unidad>("/unidades", { method: "POST", body: JSON.stringify(body) });


export interface NuevaCuenta {
  unidad_id?: string; unidad_nueva?: { tipo: "casa" | "edificio"; identificador: string; max_apartamentos?: number };
  apartamento?: string; tarifa_id?: number; dia_pago: number;
  codigo_enrolamiento?: string; es_dueno_edificio?: boolean; es_solo_contenedor?: boolean;
  tipo_acceso_virtual?: "peatonal" | "vehicular";
  titular: { nombre: string; apellido: string; email: string; telefono?: string; relacion?: string;
    dni?: string; rtn?: string; direccion_exacta?: string; profesion?: string;
    ocupacion?: string; centro_estudios?: string; lugar_trabajo?: string;
    contacto_emergencia_nombre?: string; contacto_emergencia_telefono?: string };
}
export const crearCuenta = (body: NuevaCuenta) =>
  request<{ cuenta: Cuenta; activacion: { usuario_email: string; token_activacion: string } }>(
    "/unidades/cuentas", { method: "POST", body: JSON.stringify(body) });

export const agregarMiembro = (cuentaId: string, body: object) =>
  request<{ residente: ResidenteDTO }>(`/unidades/cuentas/${cuentaId}/residentes`,
    { method: "POST", body: JSON.stringify(body) });

export const quitarMiembro = (cuentaId: string, residenteId: string) =>
  request<{ ok: boolean; message: string }>(`/unidades/cuentas/${cuentaId}/residentes/${residenteId}`,
    { method: "DELETE" });

export const regenerarEnlace = (cuentaId: string, residenteId: string) =>
  request<{ activacion: { usuario_email: string; token_activacion?: string; nota?: string } }>(
    `/unidades/cuentas/${cuentaId}/residentes/${residenteId}/regenerar-enlace`,
    { method: "POST" });

export const asignarTarjeta = (cuentaId: string, body: { card_uid: string; etiqueta?: string; residente_id?: string; tipo_acceso?: "vehicular" | "peatonal" }) =>
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
  estado: string; estado_real?: string; qr_token?: string; codigo_numerico?: string; generada_por?: string; created_at?: string;
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
    cuenta_bloqueada?: boolean;
  }>(
    "/visitas/qr/validar", { method: "POST", body: JSON.stringify({ token }) });

export const registrarAcceso = async (body: {
  visita_id: string; direccion: string; acceso_id?: number;
  foto_identidad?: Blob | null;
  foto_placa?: Blob | null;
  foto_numero_asignado?: Blob | null;
}): Promise<{ evento: object; mensaje: string }> => {
  const form = new FormData();
  form.append("visita_id", body.visita_id);
  form.append("direccion", body.direccion);
  form.append("acceso_id", String(body.acceso_id ?? 1));
  if (body.foto_identidad) form.append("foto_identidad", body.foto_identidad, "id.jpg");
  if (body.foto_placa) form.append("foto_placa", body.foto_placa, "placa.jpg");
  if (body.foto_numero_asignado) form.append("foto_numero_asignado", body.foto_numero_asignado, "numero.jpg");

  const token = getToken();
  const res = await fetch(`${API_URL}/visitas/accesos/visita`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  const json = await res.json();
  if (!res.ok) throw new Error(json.error?.message || "Error al registrar acceso");
  return json.data;
};

// NOTA: la tarjeta QR ya NO se pide al servidor. Se genera en el cliente
// (src/components/TarjetaQR.tsx) a partir del campo `qr_token` que viene en
// el JSON de la visita. Ver comentario de ese archivo para el contexto.

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
  foto_identidad?: string; foto_placa?: string; foto_numero_asignado?: string;
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
  pago_rechazado?: boolean; nota_rechazo?: string; en_revision?: boolean;
  pago?: { id: string; numero_recibo?: number; metodo: string; revisado_en?: string };
}
export interface PagoDTO {
  id: string; cuota_id: string; monto: number; metodo: string;
  referencia?: string; comprobante_archivo?: string; comprobantes?: string[];
  estado: string; nota_admin?: string; revisado_en?: string; created_at: string;
}
export interface PagoAdminDTO extends PagoDTO {
  unidad: string; periodo: string; mes_label: string;
}

export interface AbonoArregloDTO {
  abono_id: string; arreglo_id: string; numero: number; total_abonos: number;
  monto: number; fecha_pactada: string; estado: string;
}
export interface PagoHistorialDTO {
  id: string; etiqueta: string; monto: number; metodo: string;
  numero_recibo?: number; fecha: string;
}
export interface MisCuotasDTO {
  cuotas: CuotaDTO[];
  arreglo: { id: string; saldo_pendiente: number; abonos: AbonoArregloDTO[] } | null;
  historial: PagoHistorialDTO[];
}
export const misCuotas = () => request<MisCuotasDTO>("/cuotas/mias");
export const detalleCuota = (uuid: string) => request<CuotaDTO>(`/cuotas/mias/${uuid}`);

export async function subirComprobanteAbono(
  abonoUuid: string, archivo: File, monto: number, referencia: string
): Promise<PagoDTO> {
  const token = getToken();
  const form = new FormData();
  form.append("comprobante", archivo);
  form.append("monto", String(monto));
  form.append("referencia", referencia);
  const res = await fetch(`${API_URL}/cuotas/abonos/${abonoUuid}/pagar`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  const json = await res.json();
  if (!res.ok) throw new Error(json.error?.message || "Error al subir comprobante");
  return json.data;
}

export async function subirComprobante(
  cuotaUuid: string, archivos: File[], monto: number, referencia: string
): Promise<PagoDTO> {
  const token = getToken();
  const form = new FormData();
  for (const archivo of archivos) form.append("comprobante", archivo);
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
export interface PagoDetalleDTO {
  unidad: string; titular: string; monto: number; metodo: string; fecha: string | null;
}
export interface ReporteFinancieroDTO {
  periodo: string; mes_label: string; modo?: "mes" | "rango";
  total_esperado: number; total_recaudado: number; total_pendiente: number;
  pct_cobranza: number; cuentas_al_dia: number; cuentas_morosas: number;
  recaudado_por_metodo?: { efectivo: number; tarjeta_pos: number; transferencia: number; linea: number };
  al_dia: AlDiaDTO[]; morosos: MorosoDTO[]; tendencia: TendenciaDTO[];
  detalle_pagos?: PagoDetalleDTO[]; total_pagos?: number;
}
export interface MesMoraDTO {
  periodo: string; mes_label: string; monto: number; estado: string;
  vencimiento: string; dias_atraso: number;
}
export interface CasaMoraDTO {
  unidad: string; titular: string; telefono?: string | null;
  cantidad_meses: number; total_adeudado: number; meses: MesMoraDTO[]; max_dias_atraso: number;
}
export interface MoraPorCasaDTO {
  casas: CasaMoraDTO[]; total_casas_mora: number; total_general_adeudado: number; generado: string;
  aging?: { d_1_30: number; d_31_60: number; d_61_90: number; d_90_mas: number; sin_vencer: number };
  total_cuentas_activas?: number; pct_morosidad?: number;
}
export const reporteMoraPorCasa = () =>
  request<MoraPorCasaDTO>("/reportes/mora-por-casa");

// ── Reporte de caja y arqueo ──────────────────────────────────────────────
export interface CajaPorCajeroDTO {
  cajero: string; sesiones: number; efectivo: number; pos: number;
  diferencia: number; cobros: number;
}
export interface SesionReporteDTO {
  id: string; cajero: string; abierta_en: string; cerrada_en: string;
  monto_inicial: number; total_efectivo: number; total_pos: number;
  cantidad_pagos: number; diferencia_efectivo: number; diferencia_pos: number;
  cuadrada: boolean;
}
export interface ReporteCajaDTO {
  periodo_label: string; total_sesiones: number;
  total_efectivo: number; total_pos: number; total_otros: number;
  total_recaudado: number; total_diferencia: number; sesiones_descuadradas: number;
  por_cajero: CajaPorCajeroDTO[]; sesiones: SesionReporteDTO[]; generado: string;
}
export const reporteCaja = (desde?: string, hasta?: string, cajeroId?: string) => {
  const q = new URLSearchParams();
  if (desde) q.set("desde", desde);
  if (hasta) q.set("hasta", hasta);
  if (cajeroId) q.set("cajero_id", cajeroId);
  const qs = q.toString();
  return request<ReporteCajaDTO>(`/reportes/caja${qs ? "?" + qs : ""}`);
};

// ── Reporte de accesos y seguridad ────────────────────────────────────────
export interface ReporteAccesosDTO {
  periodo_label: string; total_visitas: number; total_entradas: number;
  por_tipo: { unica: number; recurrente: number; repartidor: number };
  horas_pico: { hora: string; cantidad: number }[];
  top_casas: { casa: string; visitas: number }[];
  generado: string;
}
export const reporteAccesos = (desde?: string, hasta?: string, tipo?: string) => {
  const q = new URLSearchParams();
  if (desde) q.set("desde", desde);
  if (hasta) q.set("hasta", hasta);
  if (tipo) q.set("tipo", tipo);
  const qs = q.toString();
  return request<ReporteAccesosDTO>(`/reportes/accesos${qs ? "?" + qs : ""}`);
};

export const reporteFinanciero = (anio?: number, mes?: number, desde?: string, hasta?: string) => {
  let q = "";
  if (desde && hasta) {
    q = `?desde=${desde}&hasta=${hasta}`;
  } else if (anio && mes) {
    q = `?anio=${anio}&mes=${mes}`;
  }
  return request<ReporteFinancieroDTO>(`/reportes/financiero${q}`);
};

// ── PERFIL ────────────────────────────────────────────────────────────────────
export const cambiarPassword = (passwordActual: string, passwordNueva: string) =>
  request<{ message: string; usuario: Usuario }>("/auth/cambiar-password", {
    method: "POST",
    body: JSON.stringify({ password_actual: passwordActual, password_nueva: passwordNueva }),
  });

// ── GUARDIAS ──────────────────────────────────────────────────────────────────
// Solo queda crearGuardia (usado por UsuariosAdmin). Listar/editar/reset de
// guardias se hace por el módulo Usuarios (resetPasswordUsuario, editarUsuario).
export interface GuardiaDTO {
  id: string; nombre: string; apellido: string; email: string;
  rol: string; activo: boolean; debe_cambiar_password?: boolean;
  password_generica?: string;
}
export const crearGuardia = (body: { nombre: string; apellido: string; email: string }) =>
  request<GuardiaDTO>("/guardias", { method: "POST", body: JSON.stringify(body) });

// ── HISTORIAL DE ACCESOS ──────────────────────────────────────────────────────
export interface EventoHistorialDTO {
  id: string; direccion: string; visitante: string;
  unidad: string; guardia: string; placa?: string; ocurrido_en: string;
  esta_adentro?: boolean;
  // ACCESS-04: por dónde entró/salió, y la placa que observó el guardia
  // vs la que declaró el residente al crear la visita.
  punto_acceso?: string; tranca?: string;
  placa_observada?: string; placa_no_coincide?: boolean;
  foto_identidad?: string; foto_placa?: string; foto_numero_asignado?: string;
  // Detalle completo de la visita (Día 36)
  autorizado_por?: string; tipo_visita?: string; documento_id?: string;
  telefono?: string; empresa?: string; en_vehiculo?: boolean;
  visita_creada_en?: string;
}
export interface HistorialDTO {
  eventos: EventoHistorialDTO[];
  pagina: number; por_pagina: number; total: number; total_paginas: number;
}
export const historialAccesos = (params: {
  desde?: string; hasta?: string; direccion?: string; estado?: string; buscar?: string; pagina?: number;
}) => {
  const q = new URLSearchParams();
  if (params.desde) q.set("desde", params.desde);
  if (params.hasta) q.set("hasta", params.hasta);
  if (params.direccion) q.set("direccion", params.direccion);
  if (params.estado) q.set("estado", params.estado);
  if (params.buscar) q.set("buscar", params.buscar);
  if (params.pagina) q.set("pagina", String(params.pagina));
  const qs = q.toString();
  return request<HistorialDTO>(`/dashboard/historial${qs ? "?" + qs : ""}`);
};

export interface EventoTarjetaDTO {
  id: string; direccion: string; residente: string; unidad: string;
  tarjeta: string; tipo_acceso?: "vehicular" | "peatonal"; acceso: string; ocurrido_en: string;
}
export interface HistorialTarjetasDTO {
  eventos: EventoTarjetaDTO[];
  pagina: number; por_pagina: number; total: number; total_paginas: number;
}
export const historialTarjetas = (params: {
  desde?: string; hasta?: string; direccion?: string; buscar?: string; pagina?: number;
}) => {
  const q = new URLSearchParams();
  if (params.desde) q.set("desde", params.desde);
  if (params.hasta) q.set("hasta", params.hasta);
  if (params.direccion) q.set("direccion", params.direccion);
  if (params.buscar) q.set("buscar", params.buscar);
  if (params.pagina) q.set("pagina", String(params.pagina));
  const qs = q.toString();
  return request<HistorialTarjetasDTO>(`/dashboard/historial-tarjetas${qs ? "?" + qs : ""}`);
};

// ── NOTIFICACIONES ────────────────────────────────────────────────────────────
export const contarPagosPendientes = () =>
  request<{ pendientes: number }>("/cuotas/pendientes/count");

// ── USUARIOS ──────────────────────────────────────────────────────────────────
export interface UsuarioAdminDTO {
  id: string; nombre: string; apellido: string; email: string;
  rol: string; activo: boolean; debe_cambiar_password?: boolean;
  password_generica?: string; ultimo_acceso?: string | null;
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
// Bases multi-residencial (Día 37): mismo nivel de acceso que admin, con
// las restricciones ya resueltas en el backend (no puede crear/gestionar
// a otro supervisor ni al admin dueño).
export const crearSupervisor = (body: { nombre: string; apellido: string; email: string }) =>
  request<UsuarioAdminDTO>("/usuarios/supervisores", { method: "POST", body: JSON.stringify(body) });
export const resetPasswordUsuario = (uuid: string) =>
  request<{ message: string; password_generica: string }>(`/usuarios/${uuid}/reset-password`, { method: "POST" });
export const editarUsuario = (uuid: string, body: {
  activo?: boolean; nombre?: string; apellido?: string; telefono?: string;
  dni?: string; rtn?: string; direccion_exacta?: string; profesion?: string;
  contacto_emergencia_nombre?: string; contacto_emergencia_telefono?: string;
}) =>
  request<UsuarioAdminDTO>(`/usuarios/${uuid}`, { method: "PUT", body: JSON.stringify(body) });

// ── CAJA ──────────────────────────────────────────────────────────────────────
export interface CuotaPendienteCaja { cuota_id: string; mes_label: string; monto: number; estado: string; }
export interface AbonoCajaDTO {
  arreglo_id: string; abono_id: string; numero: number; total_abonos: number;
  monto: number; fecha_pactada: string; estado: string;
}
export interface CuentaCajaDTO {
  cuenta_id: string; identificador: string; titular: string;
  residentes?: { id: string; nombre: string }[];
  cuotas_pendientes: CuotaPendienteCaja[];
  abonos_arreglo?: AbonoCajaDTO[];
}
export interface SesionCajaDTO {
  id: string; estado: string; cajero: string; monto_inicial: number;
  total_efectivo: number; total_pos: number; total_otros: number;
  total_salidas?: number;
  total_ingresos?: number;
  salidas_pendientes?: number;
  cantidad_pagos: number; efectivo_esperado: number; pos_esperado: number;
  abierta_en: string; cerrada_en?: string;
  efectivo_contado?: number; pos_contado?: number;
  diferencia_efectivo?: number; diferencia_pos?: number; nota_cierre?: string;
  pagos?: { id: string; monto: number; metodo: string; referencia?: string; hora: string }[];
}
export const estadoCaja = () => request<{ abierta: boolean; sesion?: SesionCajaDTO }>("/caja/estado");
export const saldoApertura = () => request<{ saldo_apertura: number; tiene_cierre_anterior: boolean; cerrada_en?: string }>("/caja/saldo-apertura");
export const abrirCaja = () =>
  request<SesionCajaDTO>("/caja/abrir", { method: "POST", body: JSON.stringify({}) });
export const buscarCuentaCaja = (q: string) =>
  request<CuentaCajaDTO[]>(`/caja/buscar-cuenta?q=${encodeURIComponent(q)}`);
export const registrarPagoCaja = (body: { cuota_id: string; metodo: string; referencia?: string }) =>
  request<{ pago: any; sesion: SesionCajaDTO }>("/caja/pago", { method: "POST", body: JSON.stringify(body) });
export const cerrarCaja = (body: { efectivo_contado: number; pos_contado: number; nota?: string; forzar?: boolean; desglose_billetes?: Record<string, number> }) =>
  request<SesionCajaDTO>("/caja/cerrar", { method: "POST", body: JSON.stringify(body) });
// Día 47: residencialId opcional — lo usan super_admin/desarrollador para
// elegir con cuál residencial trabajar (no pertenecen a ninguna propia). Un
// admin/cajero normal lo omite: el backend resuelve la suya automáticamente.
export const listarSesionesCaja = (residencialId?: string) =>
  request<SesionCajaDTO[]>(`/caja/sesiones${residencialId ? `?residencial_id=${residencialId}` : ""}`);
export const detalleSesionCaja = (uuid: string) => request<SesionCajaDTO>(`/caja/sesiones/${uuid}`);

// ── RESUMEN DE CAJA (saldo del sistema) ───────────────────────────────────────
export interface ResumenCajaDTO {
  saldo_inicial: number; saldo_actual: number;
  total_efectivo_historico: number; total_pos_historico: number;
  total_salidas_historico?: number;
  total_ingresos_historico?: number;
  total_ajustes?: number;
  efectivo_en_cajas_abiertas: number; cajas_abiertas: number;
  descuadres_pendientes?: number;
  salidas_pendientes?: number;
  actualizado_en?: string;
}
export const resumenCaja = (residencialId?: string) =>
  request<ResumenCajaDTO>(`/caja/resumen${residencialId ? `?residencial_id=${residencialId}` : ""}`);

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

export interface MetricasCodigoDTO {
  loc: { backend_python: number; backend_archivos: number; frontend_ts: number;
    frontend_archivos: number; css: number; total: number };
  complejidad: {
    promedio: number; rank_promedio: string; total_bloques: number;
    distribucion: Record<string, number>;
    mas_complejos: { nombre: string; archivo: string; complejidad: number; rank: string }[];
  };
  mantenibilidad: { archivo: string; mi: number; rank: string }[];
  resumen: { mi_promedio?: number };
  radon_disponible: boolean;
}
export const devMetricasCodigo = () => request<MetricasCodigoDTO>("/dev/metricas-codigo");

export interface SeguridadDTO {
  nivel_alerta: "bajo" | "medio" | "alto";
  login_fallidos_24h: number; login_fallidos_7d: number;
  bloqueos_saturacion_24h: number; bloqueos_saturacion_7d: number;
  errores_autorizacion_24h: number;
  top_ips: { ip: string; intentos: number }[];
  ataques_privilegiados: { email: string; intentos: number }[];
  timeline_7d: { dia: string; fallidos: number }[];
}
export const devSeguridad = () => request<SeguridadDTO>("/dev/seguridad");
export const devLogs = (params?: { email?: string; endpoint?: string; errores?: string; pagina?: number; residencialId?: string }) => {
  const q = new URLSearchParams();
  if (params?.email) q.set("email", params.email);
  if (params?.endpoint) q.set("endpoint", params.endpoint);
  if (params?.errores) q.set("errores", params.errores);
  if (params?.pagina) q.set("pagina", String(params.pagina));
  if (params?.residencialId) q.set("residencial_id", params.residencialId);
  return request<any>(`/dev/logs?${q.toString()}`);
};

// Configuración de hardware de las trancas (solo desarrollador)
export interface AccesoFisicoDTO {
  id: number;
  nombre: string;
  tipo: string;
  activo: boolean;
  // Día 49: 'gpio' (económico, Wiegand + relay directo a la Pi) o
  // 'modbus' (premium, Cidron por OSDP + relay externo). Se elige una
  // sola vez por punto de acceso.
  modo_control: "gpio" | "modbus";
  relay_pin: number | null;
  pulso_ms: number;
  // Modo 'gpio': pines de datos del lector Wiegand (no es un bus
  // compartido como OSDP, cada lector ocupa sus propios 2 pines).
  wiegand_d0_pin: number | null;
  wiegand_d1_pin: number | null;
  // Modo 'modbus': canal del relay externo (1-4) y dirección OSDP fija
  // del lector Cidron asignado a esta tranca en el bus compartido.
  relay_canal: number | null;
  lector_direccion_osdp: number | null;
  punto_acceso: string | null;
  direccion: string;
  // Bases multi-residencial (Día 37): a qué cliente pertenece esta tranca
  residencial: { id: string; nombre: string } | null;
}
export const devAccesosFisicos = () => request<AccesoFisicoDTO[]>("/dev/accesos-fisicos");
export const devConfigurarAcceso = (id: number, body: {
  relay_pin?: number | null; pulso_ms?: number; nombre?: string; tipo?: string;
  activo?: boolean; punto_acceso?: string; direccion?: string; residencial_id?: string | null;
  modo_control?: "gpio" | "modbus";
  wiegand_d0_pin?: number | null; wiegand_d1_pin?: number | null;
  relay_canal?: number | null; lector_direccion_osdp?: number | null;
}) =>
  request<AccesoFisicoDTO>(`/dev/accesos-fisicos/${id}`, { method: "PUT", body: JSON.stringify(body) });
export const devCrearAcceso = (body: { nombre: string; tipo: string; punto_acceso?: string; residencial_id?: string }) =>
  request<AccesoFisicoDTO>("/dev/accesos-fisicos", { method: "POST", body: JSON.stringify(body) });
export const devHistorialCount = (id: number) =>
  request<{ eventos: number }>(`/dev/accesos-fisicos/${id}/historial-count`);
export const devEliminarAcceso = (id: number) =>
  request<{ eliminado: boolean; eventos_borrados: number }>(`/dev/accesos-fisicos/${id}`, { method: "DELETE" });

// Dispositivos (Raspberry Pi)
export interface DispositivoDTO {
  id: string;
  nombre: string;
  tipo: "acceso" | "camara" | "lector_ct9";
  punto_acceso: string | null;
  activo: boolean;
  ultima_sync: string | null;
  created_at: string | null;
  token?: string;
  // Bases multi-residencial (Día 37): a qué cliente pertenece esta Pi.
  // null = sin asignar (no descarga información hasta que se le asigne).
  residencial: { id: string; nombre: string } | null;
}
export const devDispositivos = () => request<DispositivoDTO[]>("/dev/dispositivos");
export const devCrearDispositivo = (body: { nombre: string; tipo?: "acceso" | "camara" | "lector_ct9"; punto_acceso?: string; residencial_id?: string }) =>
  request<DispositivoDTO>("/dev/dispositivos", { method: "POST", body: JSON.stringify(body) });
export const devActualizarDispositivo = (id: string, body: { nombre?: string; punto_acceso?: string; activo?: boolean; residencial_id?: string | null }) =>
  request<DispositivoDTO>(`/dev/dispositivos/${id}`, { method: "PUT", body: JSON.stringify(body) });
export const devRegenerarToken = (id: string) =>
  request<DispositivoDTO>(`/dev/dispositivos/${id}/regenerar-token`, { method: "POST" });
export const devEliminarDispositivo = (id: string) =>
  request<{ eliminado: boolean }>(`/dev/dispositivos/${id}`, { method: "DELETE" });

// ── Residenciales (bases multi-residencial, Día 37) — panel desarrollador ──
// El desarrollador ve cuántos admins/clientes tiene creados y qué usuarios
// hay bajo cada uno. Hoy, en Villas del Sol, esto muestra una sola fila.
export interface UsuarioResidencialDTO {
  nombre: string; apellido: string; email: string; rol: string; activo: boolean;
}
export const devResidenciales = () => request<ResidencialDTO[]>("/dev/residenciales");
// Día 50 (corrección): consolidado en un solo endpoint todo lo que el
// desarrollador configura de una residencial — antes plan/días de
// gracia vivían en /suscripcion, separados de nombre/dirección/teléfono
// (que ni siquiera se podían editar desde acá todavía).
export const devEditarResidencial = (id: string, body: Partial<{
  nombre: string; direccion: string; telefono: string;
  plan_id: string | null; dias_gracia: number;
}>) => request<ResidencialDTO>(`/dev/residenciales/${id}`, { method: "PUT", body: JSON.stringify(body) });
export const devRegistrarPagoResidencial = (id: string) =>
  request<ResidencialDTO>(`/dev/residenciales/${id}/registrar-pago`, { method: "POST" });

// Día 50, Etapa 7 — lo que el ADMIN ve/hace de su propia suscripción
// (distinto de todo lo anterior, que es exclusivo del desarrollador).
export interface SuscripcionEstadoDTO extends ResidencialDTO {
  fecha_suspension: string | null;
  fecha_alta: string | null;
}
export interface SuscripcionPagoDTO {
  id: string;
  residencial: { id: string; nombre: string } | null;
  plan: PlanDTO | null;
  monto: number;
  es_upgrade: boolean;
  metodo: "comprobante" | "pasarela";
  comprobante_archivo: string | null;
  referencia_pasarela: string | null;
  estado: "en_revision" | "aprobado" | "rechazado";
  notas_rechazo: string | null;
  subido_por: string | null;
  revisado_por: string | null;
  revisado_en: string | null;
  created_at: string | null;
}
export const getMiSuscripcion = () => request<SuscripcionEstadoDTO>("/suscripcion/mi-estado");
export const getPlanesDisponibles = () => request<PlanDTO[]>("/suscripcion/planes-disponibles");
export const subirPlan = (planId: string, password: string) =>
  request<SuscripcionEstadoDTO>("/suscripcion/subir-plan", { method: "POST", body: JSON.stringify({ plan_id: planId, password }) });
export const getMisPagosSuscripcion = () => request<SuscripcionPagoDTO[]>("/suscripcion/mis-pagos");

// Día 50, Etapa 8 — el desarrollador revisando pagos de suscripción
// (distinto de mis-pagos, que es lo que ve el ADMIN de sus propios pagos).
export const devPagosSuscripcion = (estado?: string) =>
  request<SuscripcionPagoDTO[]>(`/dev/suscripcion-pagos${estado ? `?estado=${estado}` : ""}`);
export const devRevisarPagoSuscripcion = (id: string, decision: "aprobar" | "rechazar", notasRechazo?: string) =>
  request<SuscripcionPagoDTO>(`/dev/suscripcion-pagos/${id}/revisar`, {
    method: "POST", body: JSON.stringify({ decision, notas_rechazo: notasRechazo }),
  });
export function urlComprobanteSuscripcion(nombreArchivo: string): string {
  const token = getToken();
  return `${API_URL}/suscripcion/comprobantes/${nombreArchivo}?_auth=${token}`;
}

export async function pagarSuscripcion(archivo: File, planId?: string): Promise<SuscripcionPagoDTO> {
  const token = getToken();
  const form = new FormData();
  form.append("comprobante", archivo);
  if (planId) form.append("plan_id", planId);
  const res = await fetch(`${API_URL}/suscripcion/pagar`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  const json = await res.json();
  if (!res.ok) throw new Error(json.error?.message || "Error al subir el comprobante");
  return json.data;
}

export const devUsuariosDeResidencial = (uuid: string) =>
  request<{ residencial: ResidencialDTO; staff: UsuarioResidencialDTO[]; residentes_count: number }>(
    `/dev/residenciales/${uuid}/usuarios`);
export const devCrearResidencial = (body: {
  nombre_residencial: string; direccion: string; telefono_residencial: string;
  nombre_admin: string; apellido_admin: string; email_admin: string; telefono_admin?: string;
  plan_id: string; dias_gracia?: number;
}) => request<{ residencial: ResidencialDTO; admin: { email: string; nombre: string; password_generica: string } }>(
    "/dev/residenciales", { method: "POST", body: JSON.stringify(body) });

// Intencional: el rol desarrollador se crea una sola vez directo en la BD,
// no desde la UI. Se mantiene por si a futuro se habilita un flujo de alta.
export const crearDesarrollador = (body: { nombre: string; apellido: string; email: string }) =>
  request<UsuarioAdminDTO>("/usuarios/desarrolladores", { method: "POST", body: JSON.stringify(body) });

// ── SALDO INICIAL Y DESCUADRES ────────────────────────────────────────────────
export const modificarSaldoInicial = (saldoInicial: number, claveDev: string, residencialId?: string) =>
  request<{ saldo_inicial: number }>("/caja/saldo-inicial", {
    method: "POST", body: JSON.stringify({ saldo_inicial: saldoInicial, clave_dev: claveDev, residencial_id: residencialId }),
  });
export const ajustarSaldoConteo = (saldoReal: number, claveDev: string, motivo?: string, residencialId?: string) =>
  request<{ saldo_anterior?: number; saldo_nuevo?: number; diferencia?: number; sin_cambios?: boolean }>(
    "/caja/ajuste-conteo", {
      method: "POST", body: JSON.stringify({ saldo_real: saldoReal, clave_dev: claveDev, motivo, residencial_id: residencialId }),
    });

export interface DescuadreDTO {
  id: string; tipo: string; monto: number; motivo?: string; estado: string;
  reportado_por: string; aprobado_por?: string; created_at: string; resuelto_en?: string;
}
export const reportarDescuadre = (body: { tipo: string; monto: number; motivo?: string }) =>
  request<DescuadreDTO>("/caja/descuadre", { method: "POST", body: JSON.stringify(body) });
export const listarDescuadres = (estado?: string, residencialId?: string) => {
  const q = new URLSearchParams();
  if (estado) q.set("estado", estado);
  if (residencialId) q.set("residencial_id", residencialId);
  const qs = q.toString();
  return request<DescuadreDTO[]>(`/caja/descuadres${qs ? "?" + qs : ""}`);
};
export const resolverDescuadre = (uuid: string, accion: string, claveDev?: string) =>
  request<DescuadreDTO>(`/caja/descuadres/${uuid}/resolver`, {
    method: "POST", body: JSON.stringify({ accion, clave_dev: claveDev }),
  });

// ── HISTORIAL DE PAGOS (auditoría admin) ──────────────────────────────────────
export interface PagoHistorialItem {
  id: string; fecha: string; monto: number; metodo: string; referencia?: string;
  identificador: string; titular: string; cobrado_por: string;
  comprobante_archivo?: string | null;
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
export const listarSalidas = (estado?: string, residencialId?: string) => {
  const q = new URLSearchParams();
  if (estado) q.set("estado", estado);
  if (residencialId) q.set("residencial_id", residencialId);
  const qs = q.toString();
  return request<SalidaCajaDTO[]>(`/caja/salidas${qs ? "?" + qs : ""}`);
};
export const autorizarSalida = (uuid: string, accion: string, clave?: string) =>
  request<SalidaCajaDTO>(`/caja/salidas/${uuid}/autorizar`, {
    method: "POST", body: JSON.stringify({ accion, clave }),
  });
export const salidasPendientes = () => request<SalidaCajaDTO[]>("/caja/salidas/pendientes");

export const solicitarIngreso = (body: { monto: number; concepto: string }) =>
  request<SalidaCajaDTO>("/caja/ingreso", { method: "POST", body: JSON.stringify(body) });

// ── ARREGLOS DE PAGO ──────────────────────────────────────────────────────────
export interface AbonoDTO {
  id: string; numero: number; monto: number; fecha_pactada: string;
  estado: "pendiente" | "pagado" | "vencido"; pagado_en: string | null;
}
export interface ArregloDTO {
  id: string; estado: "activo" | "completado" | "incumplido" | "cancelado";
  deuda_total: number; abono_inicial: number; saldo_financiado: number;
  num_abonos: number; monto_por_abono: number; dias_gracia: number;
  total_abonado: number; saldo_pendiente: number; abonos_pagados: number;
  nota?: string; motivo_cierre?: string; created_at?: string; completado_en?: string;
  unidad?: string; titular?: string;
  abonos?: AbonoDTO[];
  meses_incluidos?: { mes_label: string; monto: number }[];
}

export const listarArreglos = (estado?: string) =>
  request<ArregloDTO[]>(`/arreglos${estado ? `?estado=${estado}` : ""}`);

export const detalleArreglo = (uuid: string) =>
  request<ArregloDTO>(`/arreglos/${uuid}`);

export const cuotasPendientesCuenta = (cuentaUuid: string) =>
  request<CuotaDTO[]>(`/arreglos/cuenta/${cuentaUuid}/cuotas-pendientes`);

export const crearArreglo = (body: {
  cuenta_id: string; cuotas: string[]; abono_inicial: number;
  num_abonos: number; dias_gracia: number; intervalo_dias?: number; nota?: string;
}) => request<ArregloDTO>("/arreglos", { method: "POST", body: JSON.stringify(body) });

export const cobrarAbono = (arregloUuid: string, abonoUuid: string, metodo: string, referencia?: string) =>
  request<ArregloDTO>(`/arreglos/${arregloUuid}/abonos/${abonoUuid}/cobrar`,
    { method: "POST", body: JSON.stringify({ metodo, referencia }) });

export const cancelarArreglo = (uuid: string, motivo?: string) =>
  request<ArregloDTO>(`/arreglos/${uuid}/cancelar`, { method: "POST", body: JSON.stringify({ motivo }) });

// ── RECIBOS (SAR Fase 1) ──────────────────────────────────────────────────────
export interface ConfigReciboDTO {
  nombre_emisor?: string; rtn_emisor?: string; direccion_emisor?: string;
  telefono_emisor?: string; ultimo_correlativo?: number; prefijo?: string;
  cai?: string; fase_sar_activa?: boolean;
}
// Intencional: la config del emisor de recibos se edita por API hasta que
// se construya la pantalla de configuración (recibos SAR Fase 2).
export const verConfigRecibo = () => request<ConfigReciboDTO>("/recibos/config");
export const editarConfigRecibo = (body: Partial<ConfigReciboDTO>) =>
  request<ConfigReciboDTO>("/recibos/config", { method: "PUT", body: JSON.stringify(body) });

// URL del PDF del recibo (con token de auth)
export function urlReciboPDF(pagoUuid: string): string {
  const token = getToken();
  return `${API_URL}/recibos/${pagoUuid}/pdf?_auth=${token}`;
}

export function urlConstanciaCaja(sesionUuid: string): string {
  const token = getToken();
  return `${API_URL}/caja/sesiones/${sesionUuid}/pdf?_auth=${token}`;
}

// ── SESIONES / DISPOSITIVOS ───────────────────────────────────────────────────
export interface SesionDTO {
  id: number; dispositivo: string; ip?: string;
  creada_en?: string; ultimo_uso?: string; es_actual: boolean;
}
export const listarSesiones = () => request<SesionDTO[]>("/auth/sesiones");
export const cerrarSesion = (sesionId: number) =>
  request<{ message: string }>(`/auth/sesiones/${sesionId}/cerrar`, { method: "POST" });
export const cerrarOtrasSesiones = () =>
  request<{ message: string; cerradas: number }>("/auth/sesiones/cerrar-otras", { method: "POST" });

// ── Inventario de tarjetas ────────────────────────────────────────────────
export interface TipoTarjetaDTO {
  id: string; nombre: string; tipo_acceso: "vehicular" | "peatonal";
  precio: number; stock: number; activo: boolean;
}
export interface MovimientoStockDTO {
  id: string; tipo_tarjeta: string; tipo_movimiento: string;
  cantidad: number; stock_resultante: number; nota?: string;
  registrado_por: string; created_at: string;
}
export const listarTiposTarjeta = () => request<TipoTarjetaDTO[]>("/inventario/tipos");
export const crearTipoTarjeta = (body: { nombre: string; tipo_acceso: string; precio: number; stock: number }) =>
  request<TipoTarjetaDTO>("/inventario/tipos", { method: "POST", body: JSON.stringify(body) });
export const editarTipoTarjeta = (uuid: string, body: Partial<{ nombre: string; precio: number; tipo_acceso: string; activo: boolean }>) =>
  request<TipoTarjetaDTO>(`/inventario/tipos/${uuid}`, { method: "PUT", body: JSON.stringify(body) });
export const agregarStock = (uuid: string, cantidad: number, nota?: string) =>
  request<TipoTarjetaDTO>(`/inventario/tipos/${uuid}/stock`, { method: "POST", body: JSON.stringify({ cantidad, nota }) });
export const listarMovimientosStock = () => request<MovimientoStockDTO[]>("/inventario/movimientos");

// ── Venta de tarjeta en caja ──────────────────────────────────────────────
export interface VentaTarjetaResultDTO {
  venta: { id: string; tipo_tarjeta: string; precio: number; metodo: string; created_at: string };
  tarjeta: TarjetaDTO;
  stock_restante: number;
}
export const venderTarjetaCaja = (body: {
  tipo_tarjeta_id: string; cuenta_id: string; card_uid: string;
  metodo: string; residente_id?: string; etiqueta?: string;
}) => request<VentaTarjetaResultDTO>("/caja/vender-tarjeta", { method: "POST", body: JSON.stringify(body) });

// ── Reporte de inventario de tarjetas ─────────────────────────────────────
export interface ReporteInventarioTipoDTO {
  nombre: string; tipo_acceso: string; precio: number; stock: number;
  activo: boolean; vendidas_periodo: number; recaudado_periodo: number; bajo_stock: boolean;
}
export interface ReporteInventarioDTO {
  periodo_label: string; total_vendidas: number; total_recaudado: number;
  stock_total: number; tipos_bajo_stock: number;
  tipos: ReporteInventarioTipoDTO[]; generado: string;
}
export const reporteInventario = (desde?: string, hasta?: string) => {
  const q = new URLSearchParams();
  if (desde) q.set("desde", desde);
  if (hasta) q.set("hasta", hasta);
  const qs = q.toString();
  return request<ReporteInventarioDTO>(`/reportes/inventario${qs ? "?" + qs : ""}`);
};

// ── Reporte ejecutivo (resumen del mes) ──────────────────────────────────
export interface ReporteEjecutivoDTO {
  mes_label: string; anio: number; mes: number;
  total_esperado: number; total_recaudado: number; total_pendiente: number; pct_cobranza: number;
  cartera_vencida: number; casas_en_mora: number; cuentas_activas: number; pct_morosidad: number;
  accesos_mes: number; recuperado_mora: number; pct_recuperacion: number; generado: string;
}
export const reporteEjecutivo = (anio?: number, mes?: number) => {
  const q = new URLSearchParams();
  if (anio) q.set("anio", String(anio));
  if (mes) q.set("mes", String(mes));
  const qs = q.toString();
  return request<ReporteEjecutivoDTO>(`/reportes/ejecutivo${qs ? "?" + qs : ""}`);
};

// ── Login biométrico (WebAuthn / huella) ──────────────────────────────────
export interface CredencialWebAuthnDTO {
  id: number; nombre_dispositivo: string; creada_en: string; ultimo_uso?: string | null;
}

// fetch que NO asume el wrapper {data}, para las opciones crudas de WebAuthn
async function fetchCrudo(path: string, body: unknown, conToken: boolean) {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (conToken) {
    const t = getToken();
    if (t) headers["Authorization"] = `Bearer ${t}`;
  }
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST", headers, body: JSON.stringify(body),
  });
  const json = await res.json();
  if (!res.ok) throw new Error(json.error?.message || "Error de servidor");
  return json;
}

/** Registrar la huella del dispositivo actual (usuario ya logueado). */
export async function registrarHuella(nombreDispositivo: string) {
  const opciones = await fetchCrudo("/auth/webauthn/registro/iniciar", {}, true);
  const credential = await startRegistration(opciones);
  return request<{ mensaje: string; dispositivo: CredencialWebAuthnDTO }>(
    "/auth/webauthn/registro/completar",
    { method: "POST", body: JSON.stringify({ credential, nombre_dispositivo: nombreDispositivo }) });
}

/** Entrar con huella SIN escribir correo (passkey discoverable). */
export async function loginConHuella() {
  const opciones = await fetchCrudo("/auth/webauthn/login/iniciar", {}, false);
  const credential = await startAuthentication(opciones);
  const data = await fetchCrudo("/auth/webauthn/login/completar", { credential }, false);
  setToken(data.data.token);
  return data.data.usuario as Usuario;
}

export const listarCredencialesHuella = () =>
  request<CredencialWebAuthnDTO[]>("/auth/webauthn/credenciales");
export const eliminarCredencialHuella = (id: number) =>
  request<{ mensaje: string }>(`/auth/webauthn/credenciales/${id}`, { method: "DELETE" });

/** ¿El navegador soporta WebAuthn? */
export const soportaHuella = () =>
  typeof window !== "undefined" && !!window.PublicKeyCredential;

/** Estadísticas públicas para la landing (sin login). */
export const estadisticasPublicas = () =>
  request<{ familias: number; accesos: number }>("/publico/estadisticas");

// ── Configuración global de la residencial (admin) ──────────────────────────

export interface ConfigResidencial {
  dia_pago: number;
  dias_gracia: number;
  actualizado_en: string | null;
}

export const getConfigResidencial = () =>
  request<ConfigResidencial>("/unidades/config-residencial");

export const setConfigResidencial = (body: Partial<ConfigResidencial>) =>
  request<ConfigResidencial & { cuentas_actualizadas?: number }>(
    "/unidades/config-residencial", { method: "PUT", body: JSON.stringify(body) });

// ── Mi Residencial: nombre y logo (bases multi-residencial, Día 37) ────────
// Distinto de ConfigResidencial (arriba, que es día de pago/gracia). Esto es
// la identidad visual del cliente — el mismo endpoint sirve para uno o para
// mil residenciales del futuro SaaS, porque siempre resuelve por el usuario
// que consulta.

export interface PlanDTO {
  id: string;
  nombre: string;
  max_casas: number;
  max_usuarios: number;
  almacenamiento_gb: number;
  precio_mensual: number;
  activo: boolean;
  orden: number;
  // Día 51 — niveles de plan (Básico/Premium) por flags de función.
  permite_cuotas: boolean;
  permite_notificaciones: boolean;
  // Día 53 — Sprint 2: tercer flag, para el plan Intermedio.
  permite_control_fisico: boolean;
  stats?: { residenciales: number };
}
export const devPlanes = () => request<PlanDTO[]>("/dev/planes");
export const devCrearPlan = (body: {
  nombre: string; max_casas: number; max_usuarios: number;
  almacenamiento_gb: number; precio_mensual: number; orden?: number;
  permite_cuotas?: boolean; permite_notificaciones?: boolean; permite_control_fisico?: boolean;
}) => request<PlanDTO>("/dev/planes", { method: "POST", body: JSON.stringify(body) });
export const devEditarPlan = (id: string, body: Partial<{
  nombre: string; max_casas: number; max_usuarios: number;
  almacenamiento_gb: number; precio_mensual: number; activo: boolean; orden: number;
  permite_cuotas: boolean; permite_notificaciones: boolean; permite_control_fisico: boolean;
}>) => request<PlanDTO>(`/dev/planes/${id}`, { method: "PUT", body: JSON.stringify(body) });

export interface ResidencialDTO {
  id: string;
  nombre: string;
  direccion: string | null;
  telefono: string | null;
  logo_archivo: string | null;
  // Día 47: siempre vienen con un valor (el elegido, o el de fábrica si la
  // residencial nunca lo personalizó) — nunca llegan en null.
  color_primario: string;
  color_secundario: string;
  activa: boolean;
  // Día 50 — sistema de suscripciones.
  plan: PlanDTO | null;
  fecha_proximo_pago: string | null;
  dias_gracia: number;
  suspendida: boolean;
  almacenamiento_usado_bytes: number;
  upgrade_solicitado: boolean;
  admin: { nombre: string; email: string } | null;
  created_at: string | null;
  stats?: {
    guardias: number; cajeros: number; supervisores: number;
    residentes: number; dispositivos: number;
    casas: number; usuarios_total: number;
    almacenamiento_restante_bytes: number | null;
    fecha_registro_mas_antiguo: string | null;
  };
}

export const getMiResidencial = () =>
  request<ResidencialDTO | null>("/unidades/mi-residencial");

export const setMiResidencial = (body: { nombre?: string; color_primario?: string; color_secundario?: string }) =>
  request<ResidencialDTO>("/unidades/mi-residencial", { method: "PUT", body: JSON.stringify(body) });

export async function subirLogoResidencial(archivo: File): Promise<ResidencialDTO> {
  const token = getToken();
  const form = new FormData();
  form.append("logo", archivo);
  const res = await fetch(`${API_URL}/unidades/mi-residencial/logo`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  const json = await res.json();
  if (!res.ok) throw new Error(json.error?.message || "Error al subir el logo");
  return json.data;
}

export function urlLogoResidencial(nombreArchivo: string): string {
  const token = getToken();
  return `${API_URL}/unidades/mi-residencial/logo/${nombreArchivo}?_auth=${token}`;
}

// ── Puntos de acceso (ACCESS-04, Auditoría Día 35) ──────────────────────────
// Gestión OPERATIVA para el admin: nombre, qué trancas tiene, activo/inactivo.
// El cableado real (relay_pin, pulso_ms) sigue siendo exclusivo del panel de
// desarrollador — un admin sin conocimiento técnico no debería poder tocarlo.

export interface TrancaDTO {
  id: number;
  nombre: string;
  tipo: "peatonal" | "vehicular";
  direccion: "entrada" | "salida";
  activo: boolean;
  relay_pin: number | null;
  pulso_ms: number;
  punto_acceso: string | null;
}

export interface PuntoAccesoDTO {
  punto_acceso: string;
  sin_nombre?: boolean;
  activo: boolean;
  tiene_peatonal: boolean;
  tiene_vehicular_entrada: boolean;
  tiene_vehicular_salida: boolean;
  trancas: TrancaDTO[];
}

export const listarPuntosAcceso = (soloActivos = false) =>
  request<PuntoAccesoDTO[]>(`/acceso/puntos?solo_activos=${soloActivos}`);

export const crearPuntoAcceso = (body: {
  nombre: string; peatonal: boolean; vehicular_entrada: boolean; vehicular_salida: boolean;
}) => request<PuntoAccesoDTO>("/acceso/puntos", { method: "POST", body: JSON.stringify(body) });

export const editarPuntoAcceso = (nombrePunto: string, body: { nombre?: string; activo?: boolean }) =>
  request<PuntoAccesoDTO>(
    `/acceso/puntos/${encodeURIComponent(nombrePunto)}`,
    { method: "PUT", body: JSON.stringify(body) });

export const historialCountPunto = (nombrePunto: string) =>
  request<{ eventos: number }>(
    `/acceso/puntos/${encodeURIComponent(nombrePunto)}/historial-count`);

// ── Toggle de QR recurrente por cuenta (admin) ──────────────────────────────

export const toggleQrRecurrente = (cuentaUuid: string, habilitado: boolean) =>
  request<object>(
    `/unidades/cuentas/${cuentaUuid}`,
    { method: "PUT", body: JSON.stringify({ qr_recurrente_habilitado: habilitado }) });

// Día 51 — Cuenta.activa: el interruptor manual del admin para cortarle
// el acceso a una casa a mano, sin depender del sistema de cuotas.
export const toggleCuentaActiva = (cuentaUuid: string, activa: boolean) =>
  request<object>(
    `/unidades/cuentas/${cuentaUuid}`,
    { method: "PUT", body: JSON.stringify({ activa }) });

// ── Tipo de acceso virtual (QR/BLE) por cuenta (admin) ──────────────────────
// Define qué trancas puede abrir el QR permanente y el BLE de los residentes
// de esta cuenta. Mismo concepto que el tipo_acceso de las tarjetas físicas,
// pero configurado a nivel de cuenta porque el residente activa QR/BLE
// cuando quiere, no el admin al momento de entregar una tarjeta.
export const editarTipoAccesoVirtual = (cuentaUuid: string, tipo: "peatonal" | "vehicular") =>
  request<object>(
    `/unidades/cuentas/${cuentaUuid}`,
    { method: "PUT", body: JSON.stringify({ tipo_acceso_virtual: tipo }) });

export const editarUnidad = (unidadUuid: string, body: { max_apartamentos?: number | null; max_residentes_extra?: number | null }) =>
  request<UnidadDetalle>(
    `/unidades/unidades/${unidadUuid}`,
    { method: "PUT", body: JSON.stringify(body) });
