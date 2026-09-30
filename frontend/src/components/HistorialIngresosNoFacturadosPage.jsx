import { useCallback, useEffect, useState } from 'react';

function todayIso() {
  const now = new Date();
  const offset = now.getTimezoneOffset();
  const local = new Date(now.getTime() - offset * 60000);
  return local.toISOString().slice(0, 10);
}

function primerDiaDelMesIso() {
  const hoy = todayIso();
  return `${hoy.slice(0, 7)}-01`;
}

function formatMonto(value) {
  const number = Number(value || 0);
  return number.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

const emptyFiltros = {
  desde: primerDiaDelMesIso(),
  hasta: todayIso(),
  metodo_pago_id: '',
};

function HistorialIngresosNoFacturadosPage({ isMobile, onBack }) {
  const [filtros, setFiltros] = useState(emptyFiltros);
  const [metodos, setMetodos] = useState([]);
  const [ingresos, setIngresos] = useState([]);
  const [total, setTotal] = useState('0');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const loadMetodos = async () => {
      try {
        const response = await fetch('/api/metodos-pago/', { credentials: 'include', cache: 'no-store' });
        const data = await response.json();
        if (response.ok && data.ok) {
          setMetodos(Array.isArray(data.metodos_pago) ? data.metodos_pago : []);
        }
      } catch (requestError) {
        // El selector de cuenta simplemente queda vacío si esto falla.
      }
    };
    loadMetodos();
  }, []);

  const buscar = useCallback(async (filtrosActuales) => {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams();
      if (filtrosActuales.desde) params.set('desde', filtrosActuales.desde);
      if (filtrosActuales.hasta) params.set('hasta', filtrosActuales.hasta);
      if (filtrosActuales.metodo_pago_id) params.set('metodo_pago_id', filtrosActuales.metodo_pago_id);

      const response = await fetch(`/api/admin/ingresos-no-facturados/?${params.toString()}`, {
        credentials: 'include',
        cache: 'no-store',
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo cargar el historial de ingresos no facturados.');
      }
      setIngresos(Array.isArray(data.ingresos) ? data.ingresos : []);
      setTotal(data.total || '0');
    } catch (requestError) {
      setError(requestError.message || 'No se pudo cargar el historial de ingresos no facturados.');
      setIngresos([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    buscar(filtros);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleBuscar = (event) => {
    event.preventDefault();
    buscar(filtros);
  };

  const handleLimpiar = () => {
    const limpios = emptyFiltros;
    setFiltros(limpios);
    buscar(limpios);
  };

  return (
    <section style={containerStyle(isMobile)}>
      <button type="button" onClick={onBack} style={backButtonStyle}>
        ← Volver a Disponibilidad diaria
      </button>

      <div>
        <h2 style={titleStyle(isMobile)}>Historial de ingresos no facturados</h2>
        <p style={subtitleStyle}>Dinero que entró a una cuenta sin pasar por un cobro de venta, con sus filtros de búsqueda.</p>
      </div>

      <form onSubmit={handleBuscar} style={filtrosFormStyle(isMobile)}>
        <label style={fieldStyle}>
          <span style={labelStyle}>Desde</span>
          <input
            type="date"
            value={filtros.desde}
            onChange={(event) => setFiltros((c) => ({ ...c, desde: event.target.value }))}
            style={inputStyle}
          />
        </label>
        <label style={fieldStyle}>
          <span style={labelStyle}>Hasta</span>
          <input
            type="date"
            value={filtros.hasta}
            max={todayIso()}
            onChange={(event) => setFiltros((c) => ({ ...c, hasta: event.target.value }))}
            style={inputStyle}
          />
        </label>
        <label style={fieldStyle}>
          <span style={labelStyle}>Cuenta</span>
          <select
            value={filtros.metodo_pago_id}
            onChange={(event) => setFiltros((c) => ({ ...c, metodo_pago_id: event.target.value }))}
            style={inputStyle}
          >
            <option value="">Todas</option>
            {metodos.map((metodo) => (
              <option key={metodo.id} value={metodo.id}>{metodo.nombre} ({metodo.moneda})</option>
            ))}
          </select>
        </label>
        <div style={filtrosBotonesStyle}>
          <button type="submit" style={primaryButtonStyle} disabled={loading}>
            {loading ? 'Buscando...' : 'Buscar'}
          </button>
          <button type="button" onClick={handleLimpiar} style={secondaryButtonStyle} disabled={loading}>
            Limpiar filtros
          </button>
        </div>
      </form>

      {error ? <div style={noticeStyle}>{error}</div> : null}

      {!error && !loading && ingresos.length === 0 ? (
        <div style={emptyStyle}>No hay ingresos no facturados para estos filtros.</div>
      ) : null}

      {!error && ingresos.length > 0 ? (
        <section style={panelStyle}>
          <div style={sectionTitleStyle}>
            {ingresos.length} ingreso{ingresos.length === 1 ? '' : 's'} — total ${formatMonto(total)}
          </div>
          <div style={tableWrapStyle}>
            <div style={tableStyle}>
              <div style={headStyle}>Fecha</div>
              <div style={headStyle}>Cuenta</div>
              <div style={headStyle}>Monto</div>
              <div style={headStyle}>Descripción</div>
              <div style={headStyle}>Registrado por</div>
              {ingresos.map((ingreso) => (
                <FragmentRow key={ingreso.id} ingreso={ingreso} />
              ))}
            </div>
          </div>
        </section>
      ) : null}
    </section>
  );
}

function FragmentRow({ ingreso }) {
  const montoTexto = ingreso.moneda === 'VES' && ingreso.tasa_cambio_referencia
    ? `Bs. ${formatMonto(Number(ingreso.monto) * Number(ingreso.tasa_cambio_referencia))}`
    : `$${formatMonto(ingreso.monto)}`;

  return (
    <>
      <div style={cellStyle}>{new Date(ingreso.fecha_creacion).toLocaleString('es-VE')}</div>
      <div style={cellStyle}>{ingreso.metodo_pago_nombre}</div>
      <div style={cellPrimaryStyle}>{montoTexto}</div>
      <div style={cellStyle}>{ingreso.descripcion || '—'}</div>
      <div style={cellStyle}>{ingreso.registrado_por || '—'}</div>
    </>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };
const titleStyle = (isMobile) => ({ margin: 0, color: '#fff', fontSize: isMobile ? 26 : 32 });
const subtitleStyle = { margin: '8px 0 0', color: '#d2c3c3', lineHeight: 1.6, maxWidth: 680 };

const filtrosFormStyle = (isMobile) => ({
  display: 'grid',
  gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr 1.4fr auto',
  gap: 10,
  alignItems: 'end',
  padding: 16,
  borderRadius: 18,
  border: '1px solid rgba(255,255,255,0.1)',
  background: 'linear-gradient(180deg, rgba(20,10,10,0.95) 0%, rgba(8,8,8,0.98) 100%)',
});
const fieldStyle = { display: 'grid', gap: 6 };
const labelStyle = { color: '#7fe6d3', fontSize: 12.5, fontWeight: 700 };
const inputStyle = { width: '100%', boxSizing: 'border-box', borderRadius: 10, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '9px 10px', color: '#fff', fontSize: 13 };
const filtrosBotonesStyle = { display: 'flex', gap: 8 };

const primaryButtonStyle = { border: 'none', borderRadius: 999, padding: '10px 16px', background: 'linear-gradient(90deg, #0d9488 0%, #14b8a6 100%)', color: '#04140f', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(13, 148, 136, 0.35)' };
const secondaryButtonStyle = { border: '1px solid rgba(255,255,255,0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(255,255,255,0.04)', color: '#fff', fontWeight: 700, cursor: 'pointer' };

const noticeStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid rgba(255,145,145,0.22)', background: 'rgba(255,98,98,0.12)', color: '#ffd8d8' };
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(255,255,255,0.12)', color: '#c8bbbb' };

const panelStyle = { display: 'grid', gap: 14, padding: 18, borderRadius: 20, border: '1px solid rgba(255,255,255,0.1)', background: 'linear-gradient(180deg, rgba(20,10,10,0.95) 0%, rgba(8,8,8,0.98) 100%)' };
const sectionTitleStyle = { color: '#fff', fontSize: 16, fontWeight: 700 };

const tableWrapStyle = { overflowX: 'auto' };
const tableStyle = { display: 'grid', gridTemplateColumns: '160px minmax(140px,1fr) 130px minmax(200px,1.6fr) 140px', gap: '10px 12px', alignItems: 'center', minWidth: 760 };
const headStyle = { color: '#7fe6d3', fontSize: 11.5, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em', padding: '4px 2px', borderBottom: '1px solid rgba(255,255,255,0.1)' };
const cellStyle = { color: '#fff', fontSize: 13, padding: '8px 2px', borderBottom: '1px solid rgba(255,255,255,0.06)' };
const cellPrimaryStyle = { ...cellStyle, fontWeight: 700 };

export default HistorialIngresosNoFacturadosPage;
