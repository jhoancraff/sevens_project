// Utilidades de las pantallas de cierre de turno (Cerrar turno, Cierres de turno
// y el aviso de pendientes ajenos). Los montos llegan del backend como strings
// decimales: se formatean solo para mostrarlos, nunca se reenvian formateados.
import { formatMonto } from './lotesPos';

export const TIPO_CIERRE_ESTILO = {
  normal: { color: '#bdf0cf', background: 'rgba(70,200,120,0.16)' },
  tardio: { color: '#ffe3a3', background: 'rgba(255,193,7,0.16)' },
  por_tercero: { color: '#bde0ff', background: 'rgba(59,130,246,0.18)' },
};

export const TIPO_CIERRE_ETIQUETA = {
  normal: 'Normal',
  tardio: 'Tardío',
  por_tercero: 'Cerrado por otra persona',
};

// Llamada a /api/ con credenciales; lanza Error con el mensaje del servidor si algo falla.
export async function apiCierreTurno(ruta, { method = 'GET', cuerpo } = {}) {
  const response = await fetch(`/api/${ruta}`, {
    method,
    credentials: 'include',
    cache: 'no-store',
    headers: cuerpo ? { 'Content-Type': 'application/json' } : undefined,
    body: cuerpo ? JSON.stringify(cuerpo) : undefined,
  });
  const json = await response.json().catch(() => ({}));
  if (!response.ok || !json.ok) {
    throw new Error(json.message || 'No se pudo completar la operación del cierre de turno.');
  }
  return json;
}

export function claveLinea(linea) {
  return `${linea.origen}:${linea.origen_id}`;
}

// "hace 3 h" / "hace 25 min" a partir de un instante ISO.
export function hacerCuanto(iso, ahora = Date.now()) {
  if (!iso) return '—';
  const minutos = Math.max(0, Math.round((ahora - new Date(iso).getTime()) / 60000));
  if (minutos < 60) return `hace ${minutos} min`;
  const horas = minutos / 60;
  if (horas < 48) return `hace ${horas.toFixed(horas < 10 ? 1 : 0)} h`;
  return `hace ${Math.round(horas / 24)} días`;
}

export function formatHora(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleTimeString('es-VE', { hour: '2-digit', minute: '2-digit' });
}

// Monto principal tal como lo ve la cajera en su banco: en bolivares si el metodo
// es en bolivares (con la tasa congelada del cobro), en dolares si no.
export function montoPrincipal(linea) {
  if (linea.moneda === 'VES') {
    return linea.monto_bs ? `Bs ${formatMonto(linea.monto_bs)}` : 'Bs — (sin tasa)';
  }
  return `$${formatMonto(linea.monto_usd)}`;
}

export function montoSecundario(linea) {
  return linea.moneda === 'VES' ? `$${formatMonto(linea.monto_usd)}` : '';
}

// Subtotal de un grupo de lineas en la moneda del metodo (Bs o $).
export function subtotalGrupo(lineas) {
  if (lineas.length === 0) return '';
  if (lineas[0].moneda === 'VES') {
    if (lineas.some((linea) => !linea.monto_bs)) return '';
    const total = lineas.reduce((acc, linea) => acc + Number(linea.monto_bs), 0);
    return `Bs ${formatMonto(total)}`;
  }
  return `$${formatMonto(lineas.reduce((acc, linea) => acc + Number(linea.monto_usd), 0))}`;
}

// Agrupa por metodo de pago conservando el orden de la primera aparicion.
export function agruparPorMetodo(lineas) {
  const grupos = new Map();
  lineas.forEach((linea) => {
    const clave = linea.metodo_pago_id ?? linea.metodo_pago_nombre;
    if (!grupos.has(clave)) {
      grupos.set(clave, { clave, nombre: linea.metodo_pago_nombre, esEfectivo: linea.es_efectivo, lineas: [] });
    }
    grupos.get(clave).lineas.push(linea);
  });
  return [...grupos.values()];
}
