import { useCallback, useEffect, useState } from 'react';
import AccionesActaTurno from './AccionesActaTurno';
import ConfirmModal from './ConfirmModal';
import Toast from './Toast';
import useToast from '../hooks/useToast';
import { formatFecha, formatFechaHora } from '../utils/lotesPos';
import {
  TIPO_CIERRE_ESTILO,
  TIPO_CIERRE_ETIQUETA,
  agruparPorMetodo,
  apiCierreTurno,
  formatHora,
  hacerCuanto,
  montoPrincipal,
  montoSecundario,
  subtotalGrupo,
} from '../utils/cierreTurno';

function hoyIso() {
  const ahora = new Date();
  return new Date(ahora.getTime() - ahora.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

function haceDiasIso(dias) {
  const fecha = new Date();
  fecha.setDate(fecha.getDate() - dias);
  return new Date(fecha.getTime() - fecha.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

// Cierres de turno: historial de actas, tablero de pendientes por persona y configuracion
// (activacion + umbral de cierre tardio). Administrador/contador/dueño ven todo; una
// cajera ve solo sus propios cierres (el backend filtra, ver cierre_turno_cierres_view).
function CierresTurnoPage({ isMobile, onBack, esAdmin, onCerrarTurnoDe }) {
  const [pestana, setPestana] = useState('cierres');
  const { toast, showSuccess, showError, hideToast } = useToast();

  return (
    <section style={containerStyle(isMobile)}>
      <Toast toast={toast} onClose={hideToast} />
      <div className="no-print">
        <button type="button" onClick={onBack} style={backButtonStyle}>← Volver</button>
      </div>
      <h2 style={titleStyle(isMobile)}>Cierres de turno</h2>

      <div className="no-print" style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button type="button" onClick={() => setPestana('cierres')} style={tabStyle(pestana === 'cierres')}>Cierres</button>
        {esAdmin ? (
          <>
            <button type="button" onClick={() => setPestana('pendientes')} style={tabStyle(pestana === 'pendientes')}>Pendientes</button>
            <button type="button" onClick={() => setPestana('configuracion')} style={tabStyle(pestana === 'configuracion')}>Configuración</button>
          </>
        ) : null}
      </div>

      {pestana === 'cierres' ? <PestanaCierres isMobile={isMobile} esAdmin={esAdmin} /> : null}
      {pestana === 'pendientes' && esAdmin ? <PestanaPendientes onCerrarTurnoDe={onCerrarTurnoDe} /> : null}
      {pestana === 'configuracion' && esAdmin ? (
        <PestanaConfiguracion showSuccess={showSuccess} showError={showError} />
      ) : null}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Historial de cierres
// ---------------------------------------------------------------------------
function PestanaCierres({ isMobile, esAdmin }) {
  const [filtros, setFiltros] = useState({ desde: haceDiasIso(30), hasta: hoyIso(), tipo: '', titular_id: '', soloNoLlegaron: false, soloModificados: false });
  const [cierres, setCierres] = useState([]);
  const [titulares, setTitulares] = useState([]);
  const [abierto, setAbierto] = useState(null);
  const [detalle, setDetalle] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const cargar = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const parametros = new URLSearchParams({ desde: filtros.desde, hasta: filtros.hasta });
      if (filtros.tipo) parametros.set('tipo', filtros.tipo);
      if (filtros.titular_id) parametros.set('titular_id', filtros.titular_id);
      if (filtros.soloNoLlegaron) parametros.set('con_no_llegaron', '1');
      const json = await apiCierreTurno(`cierre-turno/cierres/?${parametros.toString()}`);
      setCierres(json.cierres);
      setTitulares(json.titulares || []);
    } catch (requestError) {
      setError(requestError.message);
      setCierres([]);
    } finally {
      setLoading(false);
    }
  }, [filtros]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const abrir = async (cierre) => {
    if (abierto === cierre.id) {
      setAbierto(null);
      setDetalle(null);
      return;
    }
    setAbierto(cierre.id);
    setDetalle(null);
    try {
      const json = await apiCierreTurno(`cierre-turno/cierres/?cierre_id=${cierre.id}`);
      setDetalle(json.cierre);
    } catch (requestError) {
      setError(requestError.message);
    }
  };

  // El listado ya viene completo (hasta 300): este filtro no necesita otra consulta.
  const visibles = filtros.soloModificados ? cierres.filter((cierre) => cierre.con_modificaciones > 0) : cierres;

  const cambiar = (campo) => (event) => {
    const valor = event.target.type === 'checkbox' ? event.target.checked : event.target.value;
    setFiltros((previos) => ({ ...previos, [campo]: valor }));
  };

  return (
    <>
      <section className="no-print" style={{ ...panelStyle, gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(auto-fit, minmax(150px, 1fr))', alignItems: 'end' }}>
        <label style={labelStyle}>Desde<input type="date" value={filtros.desde} onChange={cambiar('desde')} style={inputStyle} /></label>
        <label style={labelStyle}>Hasta<input type="date" value={filtros.hasta} onChange={cambiar('hasta')} style={inputStyle} /></label>
        <label style={labelStyle}>
          Tipo
          <select value={filtros.tipo} onChange={cambiar('tipo')} style={inputStyle}>
            <option value="">Todos</option>
            {Object.entries(TIPO_CIERRE_ETIQUETA).map(([valor, etiqueta]) => <option key={valor} value={valor}>{etiqueta}</option>)}
          </select>
        </label>
        {esAdmin ? (
          <label style={labelStyle}>
            Titular
            <select value={filtros.titular_id} onChange={cambiar('titular_id')} style={inputStyle}>
              <option value="">Todos</option>
              {titulares.map((titular) => <option key={titular.id} value={titular.id}>{titular.nombre}</option>)}
            </select>
          </label>
        ) : null}
        <label style={{ ...labelStyle, flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <input type="checkbox" checked={filtros.soloNoLlegaron} onChange={cambiar('soloNoLlegaron')} />
          Solo con «no llegó»
        </label>
        <label style={{ ...labelStyle, flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <input type="checkbox" checked={filtros.soloModificados} onChange={cambiar('soloModificados')} />
          Solo modificados después del cierre
        </label>
      </section>

      {error ? <div style={noticeStyle}>{error}</div> : null}
      {loading ? <div style={emptyStyle}>Cargando cierres...</div> : null}
      {!loading && !error && visibles.length === 0 ? <div style={emptyStyle}>No hay cierres de turno en este rango.</div> : null}

      {visibles.map((cierre) => (
        <article key={cierre.id} style={cardStyle}>
          <button type="button" onClick={() => abrir(cierre)} style={cardHeaderButtonStyle}>
            <div style={{ display: 'grid', gap: 3, textAlign: 'left' }}>
              <div style={{ fontWeight: 800, color: 'var(--vg-text-strong)' }}>
                {cierre.codigo} · {cierre.titular_nombre}
                {cierre.tipo === 'por_tercero' ? <span style={mutedStyle}> · cerró {cierre.cerrado_por_nombre}</span> : null}
              </div>
              <div style={mutedStyle}>
                {formatFechaHora(cierre.fecha_cierre)} · {cierre.total_lineas} transacción(es)
                {cierre.total_no_llegaron > 0 ? ` · ${cierre.total_no_llegaron} no llegó/llegaron` : ''}
              </div>
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              {cierre.con_modificaciones > 0 ? (
                <span style={{ ...badgeStyle, color: '#ffe3a3', background: 'rgba(255,207,133,0.2)' }}>Modificado después {cierre.con_modificaciones}</span>
              ) : null}
              {cierre.total_no_llegaron > 0 ? (
                <span style={{ ...badgeStyle, color: '#ffd3d3', background: 'rgba(255,98,98,0.22)' }}>No llegó {cierre.total_no_llegaron}</span>
              ) : null}
              <span style={{ ...badgeStyle, ...TIPO_CIERRE_ESTILO[cierre.tipo] }}>{cierre.tipo_label}</span>
            </div>
          </button>
          {cierre.novedad ? <div style={novedadStyle}>Novedad: {cierre.novedad}</div> : null}
          {abierto === cierre.id ? <ActaDetalle cierre={detalle} /> : null}
        </article>
      ))}
    </>
  );
}

function ActaDetalle({ cierre }) {
  if (!cierre) return <div style={mutedStyle}>Cargando acta...</div>;
  const grupos = agruparPorMetodo(cierre.lineas);
  return (
    <div style={{ display: 'grid', gap: 10, paddingTop: 6 }}>
      <AccionesActaTurno cierreId={cierre.id} />
      <div style={mutedStyle}>
        Titular: {cierre.titular_nombre}{cierre.titular_rol ? ` (${cierre.titular_rol})` : ''} · Cerrado por:{' '}
        {cierre.cerrado_por_nombre}{cierre.cerrado_por_rol ? ` (${cierre.cerrado_por_rol})` : ''} · Desde {formatFechaHora(cierre.desde)} hasta {formatFechaHora(cierre.hasta)}
      </div>
      {grupos.map((grupo) => (
        <div key={grupo.clave} style={{ display: 'grid', gap: 6 }}>
          <div style={subTitleStyle}>{grupo.nombre} · {grupo.lineas.length} · {subtotalGrupo(grupo.lineas)}</div>
          {grupo.lineas.map((linea) => (
            <div key={linea.id} style={lineaActaStyle(linea.estado)}>
              <div>
                <strong>{montoPrincipal(linea)}</strong>
                {montoSecundario(linea) ? <span style={mutedStyle}> · {montoSecundario(linea)}</span> : null}
                <div style={detalleLineaStyle}>
                  {formatHora(linea.fecha_transaccion)} · {linea.concepto}{linea.cliente ? ` · ${linea.cliente}` : ''}
                  {linea.referencia && !String(linea.referencia).startsWith('ABONO-') ? ` · Ref: ${linea.referencia}` : ''}
                </div>
                {linea.nota ? <div style={{ ...detalleLineaStyle, color: '#ffd3d3' }}>Nota: {linea.nota}</div> : null}
                {(linea.modificaciones || []).map((cambio) => (
                  <div key={cambio.tipo} style={modificadoStyle}>
                    Modificado después del cierre: {cambio.detalle}
                    {cambio.por ? ` Lo hizo ${cambio.por}${cambio.fecha ? ` el ${formatFechaHora(cambio.fecha)}` : ''}.` : ''}
                    {cambio.motivo ? ` Motivo: ${cambio.motivo}` : ''}
                  </div>
                ))}
              </div>
              <span style={{ ...badgeStyle, ...(linea.estado === 'confirmada' ? TIPO_CIERRE_ESTILO.normal : { color: '#ffd3d3', background: 'rgba(255,98,98,0.22)' }) }}>
                {linea.estado_label}
              </span>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tablero de pendientes (quien tiene transacciones sin cerrar)
// ---------------------------------------------------------------------------
function PestanaPendientes({ onCerrarTurnoDe }) {
  const [estado, setEstado] = useState(null);
  const [error, setError] = useState('');

  const cargar = useCallback(async () => {
    setError('');
    try {
      setEstado(await apiCierreTurno('cierre-turno/estado/'));
    } catch (requestError) {
      setError(requestError.message);
    }
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  if (error) return <div style={noticeStyle}>{error}</div>;
  if (!estado) return <div style={emptyStyle}>Cargando pendientes...</div>;
  if (!estado.activo) return <div style={noticeStyle}>El cierre de turno no está activado. Actívalo en la pestaña Configuración.</div>;
  if (estado.pendientes.length === 0) return <div style={emptyStyle}>Nadie tiene transacciones sin cerrar.</div>;

  return (
    <section style={panelStyle}>
      <div style={sectionTitleStyle}>Transacciones sin cerrar</div>
      {estado.pendientes.map((fila) => {
        const alerta = fila.horas_pendiente > estado.umbral_tardio_horas;
        return (
          <div key={fila.titular_id} style={{ ...filaStyle, borderColor: alerta ? 'rgba(255,193,7,0.5)' : undefined }}>
            <div>
              <strong>{fila.titular_nombre}</strong>
              <span style={mutedStyle}> · {fila.titular_rol || 'sin rol'} · {fila.cantidad} sin cerrar · la más vieja {hacerCuanto(fila.mas_antigua)}</span>
              {alerta ? <span style={{ ...badgeStyle, ...TIPO_CIERRE_ESTILO.tardio, marginLeft: 8 }}>Pasó el umbral de {estado.umbral_tardio_horas} h</span> : null}
            </div>
            <button type="button" onClick={() => onCerrarTurnoDe && onCerrarTurnoDe(fila.titular_id)} style={secondaryButtonStyle}>
              {fila.es_mio ? 'Cerrar mi turno' : 'Cerrar su turno'}
            </button>
          </div>
        );
      })}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Configuracion
// ---------------------------------------------------------------------------
function PestanaConfiguracion({ showSuccess, showError }) {
  const [config, setConfig] = useState(null);
  const [horas, setHoras] = useState('20');
  const [saving, setSaving] = useState(false);
  const [confirmActivar, setConfirmActivar] = useState(false);

  const cargar = useCallback(async () => {
    try {
      const json = await apiCierreTurno('admin/cierre-turno/config/');
      setConfig(json);
      setHoras(String(json.umbral_tardio_horas));
    } catch (requestError) {
      showError(requestError.message);
    }
  }, [showError]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const enviar = async (cuerpo) => {
    setSaving(true);
    try {
      const json = await apiCierreTurno('admin/cierre-turno/config/', { method: 'POST', cuerpo });
      setConfig(json);
      setHoras(String(json.umbral_tardio_horas));
      showSuccess(json.message);
    } catch (requestError) {
      showError(requestError.message);
    } finally {
      setSaving(false);
      setConfirmActivar(false);
    }
  };

  if (!config) return <div style={emptyStyle}>Cargando configuración...</div>;

  return (
    <section style={panelStyle}>
      <div style={sectionTitleStyle}>Activación</div>
      {config.activo ? (
        <div style={{ color: 'var(--vg-f-8fffb0)', fontWeight: 700 }}>
          Activo desde el {formatFecha(config.fecha_activacion)}. Desde ese día cuentan las transacciones pendientes de cierre.
        </div>
      ) : (
        <>
          <div style={mutedStyle}>
            Inactivo: no hay pendientes y nada bloquea el cierre diario. Al activarlo, las transacciones de hoy en adelante
            (cobros que no son de punto de venta y propinas) deberán cerrarse por turno.
          </div>
          <button type="button" disabled={saving} onClick={() => setConfirmActivar(true)} style={secondaryButtonStyle}>
            Activar cierre de turno
          </button>
        </>
      )}

      <div style={{ ...sectionTitleStyle, marginTop: 8 }}>Cierre tardío</div>
      <div style={mutedStyle}>
        Si quien cierra su propio turno tiene una transacción pendiente de hace más horas que este umbral, el cierre se registra como tardío y exige novedad.
      </div>
      <form
        onSubmit={(event) => { event.preventDefault(); enviar({ action: 'umbral', horas }); }}
        style={{ display: 'flex', gap: 10, alignItems: 'end', flexWrap: 'wrap' }}
      >
        <label style={labelStyle}>
          Horas
          <input type="number" min="1" step="1" value={horas} onChange={(event) => setHoras(event.target.value)} style={{ ...inputStyle, width: 120 }} />
        </label>
        <button type="submit" disabled={saving} style={secondaryButtonStyle}>Guardar umbral</button>
      </form>

      <ConfirmModal
        open={confirmActivar}
        busy={saving}
        title="¿Activar el cierre de turno?"
        confirmLabel="Activar"
        onCancel={() => setConfirmActivar(false)}
        onConfirm={() => enviar({ action: 'activar' })}
        message="Desde el inicio de hoy, cobros y propinas quedarán pendientes hasta que cada persona cierre su turno. Esto no se puede revertir desde aquí."
      />
    </section>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const titleStyle = (isMobile) => ({ margin: 0, color: 'var(--vg-text-strong)', fontSize: isMobile ? 26 : 34 });
const panelStyle = { display: 'grid', gap: 12, padding: 18, borderRadius: 20, border: '1px solid rgba(var(--vg-ink), 0.1)', background: 'linear-gradient(180deg, var(--vg-bg-card) 0%, var(--vg-s-080808-a980) 100%)' };
const cardStyle = { display: 'grid', gap: 10, padding: '14px 16px', borderRadius: 16, border: '1px solid rgba(var(--vg-ink), 0.1)', background: 'rgba(var(--vg-ink), 0.03)' };
const cardHeaderButtonStyle = { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap', width: '100%', border: 'none', background: 'none', padding: 0, cursor: 'pointer', color: 'inherit', font: 'inherit' };
const sectionTitleStyle = { color: 'var(--vg-text-strong)', fontSize: 19, fontWeight: 700 };
const subTitleStyle = { color: 'var(--vg-f-ffb0b0)', fontSize: 12, fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase' };
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(var(--vg-ink), 0.12)', color: 'var(--vg-f-c8bbbb)', padding: 12, textAlign: 'center' };
const noticeStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid var(--vg-f-ff9191-a220)', background: 'rgba(255,98,98,0.12)', color: 'var(--vg-f-ffd8d8)' };
const mutedStyle = { color: 'var(--vg-f-a89999)', fontSize: 12.5 };
const novedadStyle = { padding: '8px 12px', borderRadius: 10, background: 'rgba(var(--vg-ink), 0.05)', color: 'var(--vg-f-f2e6e6)', fontSize: 13.5, overflowWrap: 'anywhere' };
const filaStyle = { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap', padding: '10px 12px', borderRadius: 12, border: '1px solid rgba(var(--vg-ink), 0.1)', background: 'rgba(var(--vg-ink), 0.03)', color: 'var(--vg-f-f2e6e6)' };
const lineaActaStyle = (estado) => ({ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap', padding: '8px 12px', borderRadius: 10, border: `1px solid ${estado === 'confirmada' ? 'rgba(70,200,120,0.3)' : 'rgba(255,98,98,0.5)'}`, background: estado === 'confirmada' ? 'rgba(70,200,120,0.05)' : 'rgba(255,98,98,0.08)', color: 'var(--vg-f-f2e6e6)' });
const modificadoStyle = { color: '#ffe3a3', fontSize: 12.5, fontWeight: 700, overflowWrap: 'anywhere' };
const detalleLineaStyle = { color: 'var(--vg-f-d2c3c3)', fontSize: 12.5, overflowWrap: 'anywhere' };
const badgeStyle = { fontSize: 11, fontWeight: 800, padding: '3px 10px', borderRadius: 999, textTransform: 'uppercase', letterSpacing: '0.04em' };
const labelStyle = { display: 'grid', gap: 6, color: 'var(--vg-f-f2e6e6)', fontSize: 13 };
const inputStyle = { borderRadius: 12, border: '1px solid rgba(var(--vg-ink), 0.14)', background: 'var(--vg-s-161010)', padding: '10px 12px', color: 'var(--vg-text-strong)', boxSizing: 'border-box', font: 'inherit' };
const secondaryButtonStyle = { border: '1px solid rgba(var(--vg-ink), 0.18)', borderRadius: 999, padding: '9px 16px', background: 'rgba(var(--vg-ink), 0.05)', color: 'var(--vg-text-strong)', fontWeight: 700, cursor: 'pointer', width: 'fit-content' };
const tabStyle = (activo) => ({ border: `1px solid ${activo ? 'rgba(59,130,246,0.7)' : 'rgba(var(--vg-ink), 0.18)'}`, borderRadius: 999, padding: '9px 18px', background: activo ? 'rgba(59,130,246,0.22)' : 'rgba(var(--vg-ink), 0.05)', color: 'var(--vg-text-strong)', fontWeight: 700, cursor: 'pointer' });
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };

export default CierresTurnoPage;
