import { useCallback, useEffect, useMemo, useState } from 'react';

function todayYearMonth() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

function formatMonto(value) {
  const number = Number(value || 0);
  return number.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatFechaLarga(iso) {
  const [anio, mes, dia] = iso.split('-').map(Number);
  const fecha = new Date(anio, mes - 1, dia);
  return fecha.toLocaleDateString('es-VE', { weekday: 'long', day: 'numeric', month: 'long' });
}

function agruparBancos(metodos) {
  const porClave = new Map();
  const orden = [];
  for (const metodo of metodos) {
    const clave = metodo.cuenta_bancaria || `__metodo_${metodo.id}`;
    if (!porClave.has(clave)) {
      porClave.set(clave, {
        clave,
        nombre: metodo.cuenta_bancaria || metodo.nombre,
        agrupado: Boolean(metodo.cuenta_bancaria),
        moneda: metodo.moneda,
        monedaMixta: false,
        metodos: [],
      });
      orden.push(clave);
    }
    const banco = porClave.get(clave);
    banco.metodos.push(metodo);
    if (banco.moneda !== metodo.moneda) banco.monedaMixta = true;
  }
  return orden.map((clave) => porClave.get(clave));
}

function ReporteFlujoBancoPage({ isMobile, onBack }) {
  const [bancos, setBancos] = useState([]);
  const [bancoClave, setBancoClave] = useState('');
  const [anioMes, setAnioMes] = useState(todayYearMonth());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [detalleSeleccionado, setDetalleSeleccionado] = useState(null); // { fecha, tipo }
  const [detalleData, setDetalleData] = useState(null);
  const [loadingDetalle, setLoadingDetalle] = useState(false);

  useEffect(() => {
    const loadMetodos = async () => {
      try {
        const response = await fetch('/api/metodos-pago/', { credentials: 'include', cache: 'no-store' });
        const json = await response.json();
        if (response.ok && json.ok) {
          const agrupados = agruparBancos(Array.isArray(json.metodos_pago) ? json.metodos_pago : []);
          setBancos(agrupados);
          if (agrupados.length > 0) {
            setBancoClave(agrupados[0].clave);
          }
        }
      } catch (requestError) {
        setError('No se pudieron cargar las cuentas.');
      }
    };
    loadMetodos();
  }, []);

  const bancoActual = useMemo(() => bancos.find((banco) => banco.clave === bancoClave) || null, [bancos, bancoClave]);

  const loadResumen = useCallback(async (banco, periodo) => {
    if (!banco) return;
    setLoading(true);
    setError('');
    try {
      const [anio, mes] = periodo.split('-');
      const ids = banco.metodos.map((metodo) => metodo.id).join(',');
      const response = await fetch(
        `/api/admin/reportes/flujo-banco/?anio=${anio}&mes=${Number(mes)}&metodo_pago_ids=${ids}`,
        { credentials: 'include', cache: 'no-store' },
      );
      const json = await response.json();
      if (!response.ok || !json.ok) {
        throw new Error(json.message || 'No se pudo cargar el flujo del banco.');
      }
      setData(json);
    } catch (requestError) {
      setError(requestError.message || 'No se pudo cargar el flujo del banco.');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (bancoActual) {
      setDetalleSeleccionado(null);
      loadResumen(bancoActual, anioMes);
    }
  }, [bancoActual, anioMes, loadResumen]);

  const abrirDetalle = async (fecha, tipo) => {
    setDetalleSeleccionado({ fecha, tipo });
    setLoadingDetalle(true);
    setDetalleData(null);
    try {
      const ids = bancoActual.metodos.map((metodo) => metodo.id).join(',');
      const response = await fetch(
        `/api/admin/reportes/flujo-banco/detalle/?fecha=${fecha}&tipo=${tipo}&metodo_pago_ids=${ids}`,
        { credentials: 'include', cache: 'no-store' },
      );
      const json = await response.json();
      if (!response.ok || !json.ok) {
        throw new Error(json.message || 'No se pudo cargar el detalle de ese día.');
      }
      setDetalleData(json);
    } catch (requestError) {
      setError(requestError.message || 'No se pudo cargar el detalle de ese día.');
    } finally {
      setLoadingDetalle(false);
    }
  };

  const volverAlResumen = () => {
    setDetalleSeleccionado(null);
    setDetalleData(null);
  };

  const dias = data?.dias || [];
  const moneda = data?.moneda;

  return (
    <section style={containerStyle(isMobile)}>
      <div className="no-print" style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <button type="button" onClick={detalleSeleccionado ? volverAlResumen : onBack} style={backButtonStyle}>
          {detalleSeleccionado ? '← Volver al resumen del mes' : '← Volver a Contabilidad'}
        </button>
        <button type="button" onClick={() => window.print()} style={printButtonStyle}>
          Imprimir / Guardar PDF
        </button>
      </div>

      <div>
        <h2 style={titleStyle(isMobile)}>Flujo de banco diario</h2>
        <p style={subtitleStyle}>Entradas y salidas día por día de una cuenta digital, para cuadrar contra el estado de cuenta real del banco.</p>
      </div>

      <div className="no-print" style={filtersRowStyle(isMobile)}>
        <label style={fieldStyle}>
          <span style={labelStyle}>Banco / cuenta</span>
          <select value={bancoClave} onChange={(event) => setBancoClave(event.target.value)} style={inputStyle}>
            {bancos.map((banco) => (
              <option key={banco.clave} value={banco.clave}>
                {banco.nombre} ({banco.moneda}){banco.agrupado ? ` — ${banco.metodos.length} métodos` : ''}
              </option>
            ))}
          </select>
        </label>
        <label style={fieldStyle}>
          <span style={labelStyle}>Mes</span>
          <input type="month" value={anioMes} max={todayYearMonth()} onChange={(event) => setAnioMes(event.target.value)} style={inputStyle} />
        </label>
      </div>

      {loading ? <div style={emptyStyle}>Cargando reporte...</div> : null}
      {!loading && error ? <div style={noticeStyle}>{error}</div> : null}

      {!loading && !error && data && !detalleSeleccionado ? (
        <section style={panelStyle}>
          <div style={sectionTitleStyle}>{bancoActual?.nombre} — {anioMes}</div>

          <div style={tableWrapStyle}>
            <div style={tableStyle}>
              <div style={headStyle}>Fecha</div>
              <div style={headStyle}>Entrada</div>
              <div style={headStyle}>Salida</div>
              {dias.map((dia) => (
                <FilaDia key={dia.fecha} dia={dia} moneda={moneda} onAbrirDetalle={abrirDetalle} />
              ))}
              <div style={{ ...cellStyle, fontWeight: 800 }}>Total del mes</div>
              <div style={{ ...cellStyle, fontWeight: 800, color: '#8fffb0' }}>${formatMonto(data.totales.entrada)}</div>
              <div style={{ ...cellStyle, fontWeight: 800, color: '#ff9d9d' }}>${formatMonto(data.totales.salida)}</div>
            </div>
          </div>

          <div style={summaryStyle}>
            Neto del mes:{' '}
            <span style={{ color: Number(data.totales.neto) >= 0 ? '#8fffb0' : '#ff9d9d', fontWeight: 800 }}>
              ${formatMonto(data.totales.neto)}
            </span>
          </div>
        </section>
      ) : null}

      {!loading && !error && detalleSeleccionado ? (
        <section style={panelStyle}>
          <div style={sectionTitleStyle}>
            {detalleSeleccionado.tipo === 'entrada' ? 'Entradas' : 'Salidas'} — {formatFechaLarga(detalleSeleccionado.fecha)}
          </div>

          {loadingDetalle ? <div style={emptyStyle}>Cargando detalle...</div> : null}

          {!loadingDetalle && detalleData ? (
            detalleData.movimientos.length === 0 ? (
              <div style={emptyStyle}>No hay movimientos de este tipo en este día.</div>
            ) : (
              <div style={tableWrapStyle}>
                <div style={detalleTableStyle}>
                  <div style={headStyle}>Hora</div>
                  <div style={headStyle}>Método</div>
                  <div style={headStyle}>Origen</div>
                  <div style={headStyle}>Referencia</div>
                  <div style={headStyle}>Monto</div>
                  {detalleData.movimientos.map((movimiento, index) => (
                    <FragmentMovimiento key={index} movimiento={movimiento} moneda={detalleData.moneda} />
                  ))}
                </div>
              </div>
            )
          ) : null}
        </section>
      ) : null}
    </section>
  );
}

function FilaDia({ dia, moneda, onAbrirDetalle }) {
  const tieneEntrada = Number(dia.entrada) > 0;
  const tieneSalida = Number(dia.salida) > 0;

  const montoCelda = (tipo, monto, montoLocal, activo) => {
    const texto = moneda === 'VES' && montoLocal !== null
      ? `Bs. ${formatMonto(montoLocal)}`
      : `$${formatMonto(monto)}`;
    if (!activo) {
      return <div style={cellStyle}>{texto}</div>;
    }
    return (
      <button type="button" onClick={() => onAbrirDetalle(dia.fecha, tipo)} style={montoClicableStyle(tipo)}>
        {texto}
      </button>
    );
  };

  return (
    <>
      <div style={cellStyle}>{dia.fecha}</div>
      {montoCelda('entrada', dia.entrada, dia.entrada_local, tieneEntrada)}
      {montoCelda('salida', dia.salida, dia.salida_local, tieneSalida)}
    </>
  );
}

function FragmentMovimiento({ movimiento, moneda }) {
  return (
    <>
      <div style={cellStyle}>{movimiento.hora || '—'}</div>
      <div style={cellStyle}>{movimiento.metodo_pago || '—'}</div>
      <div style={cellStyle}>{movimiento.origen}</div>
      <div style={cellStyle}>{movimiento.referencia || '—'}</div>
      <div style={cellStyle}>
        {moneda === 'VES' && movimiento.monto_local !== null
          ? `Bs. ${formatMonto(movimiento.monto_local)}`
          : `$${formatMonto(movimiento.monto_usd)}`}
      </div>
    </>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const titleStyle = (isMobile) => ({ margin: 0, color: '#fff', fontSize: isMobile ? 28 : 34 });
const subtitleStyle = { margin: '8px 0 0', color: '#d2c3c3', maxWidth: 680, lineHeight: 1.6 };
const filtersRowStyle = (isMobile) => ({
  display: 'flex',
  gap: 14,
  flexWrap: 'wrap',
  alignItems: isMobile ? 'stretch' : 'flex-end',
  flexDirection: isMobile ? 'column' : 'row',
});
const fieldStyle = { display: 'grid', gap: 6 };
const labelStyle = { color: '#f2e6e6', fontSize: 13, fontWeight: 700 };
const inputStyle = { borderRadius: 12, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '10px 12px', color: '#fff', fontSize: 14 };
const panelStyle = { display: 'grid', gap: 14, padding: 18, borderRadius: 20, border: '1px solid rgba(255,255,255,0.1)', background: 'linear-gradient(180deg, rgba(20,10,10,0.95) 0%, rgba(8,8,8,0.98) 100%)' };
const sectionTitleStyle = { color: '#fff', fontSize: 19, fontWeight: 700, textTransform: 'capitalize' };
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(255,255,255,0.12)', color: '#c8bbbb' };
const noticeStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid rgba(255,145,145,0.22)', background: 'rgba(255,98,98,0.12)', color: '#ffd8d8' };
const printButtonStyle = { border: '1px solid rgba(255,255,255,0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(255,255,255,0.04)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };
const summaryStyle = { color: '#c8bbbb', fontSize: 14 };

const tableWrapStyle = { overflowX: 'auto' };
const tableStyle = { display: 'grid', gridTemplateColumns: 'minmax(120px,0.7fr) minmax(140px,1fr) minmax(140px,1fr)', gap: '4px 12px', alignItems: 'center', minWidth: 480 };
const detalleTableStyle = { display: 'grid', gridTemplateColumns: 'minmax(70px,0.5fr) minmax(120px,0.8fr) minmax(160px,1.2fr) minmax(120px,0.8fr) minmax(110px,0.7fr)', gap: '4px 12px', alignItems: 'center', minWidth: 700 };
const headStyle = { color: '#f0b4b4', fontSize: 11, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em', padding: '4px 2px', borderBottom: '1px solid rgba(255,255,255,0.1)' };
const cellStyle = { color: '#f2e6e6', fontSize: 13, padding: '6px 2px', borderBottom: '1px solid rgba(255,255,255,0.05)' };
const montoClicableStyle = (tipo) => ({
  ...cellStyle,
  textAlign: 'left',
  border: 'none',
  background: 'transparent',
  cursor: 'pointer',
  fontWeight: 700,
  color: tipo === 'entrada' ? '#8fffb0' : '#ff9d9d',
  textDecoration: 'underline',
  textUnderlineOffset: 3,
});

export default ReporteFlujoBancoPage;
