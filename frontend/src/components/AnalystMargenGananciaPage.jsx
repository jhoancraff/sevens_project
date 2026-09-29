import { useCallback, useEffect, useMemo, useState } from 'react';

function toIso(date) {
  const offset = date.getTimezoneOffset();
  const local = new Date(date.getTime() - offset * 60000);
  return local.toISOString().slice(0, 10);
}

function todayIso() {
  return toIso(new Date());
}

function startOfWeekIso() {
  const now = new Date();
  const day = now.getDay();
  const diff = day === 0 ? 6 : day - 1;
  const monday = new Date(now);
  monday.setDate(now.getDate() - diff);
  return toIso(monday);
}

function startOfMonthIso() {
  const now = new Date();
  return toIso(new Date(now.getFullYear(), now.getMonth(), 1));
}

function startOfYearIso() {
  const now = new Date();
  return toIso(new Date(now.getFullYear(), 0, 1));
}

function yesterdayIso() {
  const now = new Date();
  now.setDate(now.getDate() - 1);
  return toIso(now);
}

function formatMonto(value) {
  const number = Number(value || 0);
  return number.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatFechaHora(iso) {
  const fecha = new Date(iso);
  const fechaTexto = fecha.toLocaleDateString('es-VE', { day: 'numeric', month: 'numeric' });
  const horaTexto = fecha.toLocaleTimeString('es-VE', { hour: '2-digit', minute: '2-digit' });
  return `${fechaTexto}, ${horaTexto}`;
}

const PRESETS = [
  { label: 'Hoy', get: () => ({ desde: todayIso(), hasta: todayIso() }) },
  { label: 'Ayer', get: () => ({ desde: yesterdayIso(), hasta: yesterdayIso() }) },
  { label: 'Esta semana', get: () => ({ desde: startOfWeekIso(), hasta: todayIso() }) },
  { label: 'Este mes', get: () => ({ desde: startOfMonthIso(), hasta: todayIso() }) },
  { label: 'Este año', get: () => ({ desde: startOfYearIso(), hasta: todayIso() }) },
];

function AnalystMargenGananciaPage({ isMobile, onBack }) {
  const [desde, setDesde] = useState(todayIso());
  const [hasta, setHasta] = useState(todayIso());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busqueda, setBusqueda] = useState('');
  const [isSearchFocused, setIsSearchFocused] = useState(false);
  const [productoSeleccionadoId, setProductoSeleccionadoId] = useState(null);

  const loadReport = useCallback(async (desdeConsultado, hastaConsultado) => {
    setLoading(true);
    setError('');
    try {
      const response = await fetch(
        `/api/admin/reportes/margen-ganancia-detalle/?desde=${desdeConsultado}&hasta=${hastaConsultado}`,
        { credentials: 'include', cache: 'no-store' },
      );
      const json = await response.json();
      if (!response.ok || !json.ok) {
        throw new Error(json.message || 'No se pudo cargar el reporte de margen de ganancia.');
      }
      setData(json);
    } catch (requestError) {
      setError(requestError.message || 'No se pudo cargar el reporte de margen de ganancia.');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadReport(desde, hasta);
  }, [desde, hasta, loadReport]);

  useEffect(() => {
    setBusqueda('');
    setProductoSeleccionadoId(null);
  }, [desde, hasta]);

  const applyPreset = (preset) => {
    const range = preset.get();
    setDesde(range.desde);
    setHasta(range.hasta);
  };

  const productos = useMemo(() => data?.productos || [], [data]);

  const busquedaQuery = busqueda.trim().toLowerCase();
  const coincidencias = useMemo(() => {
    if (!busquedaQuery) return [];
    return productos.filter((producto) => producto.nombre.toLowerCase().includes(busquedaQuery)).slice(0, 5);
  }, [productos, busquedaQuery]);

  const handleBusquedaChange = (value) => {
    // Escribir SIEMPRE invalida una seleccion anterior — el filtro solo se
    // vuelve a aplicar cuando el usuario elige otra coincidencia de la lista.
    setBusqueda(value);
    setProductoSeleccionadoId(null);
  };

  const handleSeleccionarProducto = (producto) => {
    setBusqueda(producto.nombre);
    setProductoSeleccionadoId(producto.producto_id);
    setIsSearchFocused(false);
  };

  const handleQuitarFiltro = () => {
    setBusqueda('');
    setProductoSeleccionadoId(null);
  };

  const productosVisibles = productoSeleccionadoId
    ? productos.filter((producto) => producto.producto_id === productoSeleccionadoId)
    : productos;

  const totales = data?.totales;

  return (
    <section style={containerStyle(isMobile)}>
      <div className="no-print" style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <button type="button" onClick={onBack} style={backButtonStyle}>
          ← Volver a Contabilidad
        </button>
        <button type="button" onClick={() => window.print()} style={printButtonStyle}>
          Imprimir / Guardar PDF
        </button>
      </div>

      <div>
        <h2 style={titleStyle(isMobile)}>Margen de ganancia por plato</h2>
      </div>

      <div className="no-print" style={filtersRowStyle(isMobile)}>
        <label style={dateLabelStyle}>
          Desde
          <input type="date" value={desde} max={hasta} onChange={(event) => setDesde(event.target.value)} style={dateInputStyle} />
        </label>
        <label style={dateLabelStyle}>
          Hasta
          <input type="date" value={hasta} max={todayIso()} onChange={(event) => setHasta(event.target.value)} style={dateInputStyle} />
        </label>
        <div style={presetsWrapStyle}>
          {PRESETS.map((preset) => (
            <button key={preset.label} type="button" onClick={() => applyPreset(preset)} style={presetButtonStyle}>
              {preset.label}
            </button>
          ))}
        </div>
      </div>

      {loading ? <div style={emptyStyle}>Cargando reporte...</div> : null}
      {!loading && error ? <div style={noticeStyle}>{error}</div> : null}

      {!loading && !error && data ? (
        <section style={panelStyle}>
          <div style={sectionTitleStyle}>
            {desde === hasta ? `Ventas del ${desde}` : `Ventas del ${desde} al ${hasta}`}
          </div>

          <div className="no-print" style={{ ...fieldStyle, position: 'relative', maxWidth: 420 }}>
            <input
              type="text"
              value={busqueda}
              onChange={(event) => handleBusquedaChange(event.target.value)}
              onFocus={() => setIsSearchFocused(true)}
              onBlur={() => setTimeout(() => setIsSearchFocused(false), 150)}
              placeholder="Buscar producto por nombre..."
              style={searchInputStyle}
              autoComplete="off"
            />
            {isSearchFocused && busquedaQuery && coincidencias.length > 0 ? (
              <div style={suggestionsPanelStyle}>
                {coincidencias.map((producto) => (
                  <button
                    key={producto.producto_id}
                    type="button"
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => handleSeleccionarProducto(producto)}
                    style={suggestionRowStyle}
                  >
                    <span style={{ color: '#fff', fontWeight: 600 }}>{producto.nombre}</span>
                    <span style={{ color: '#e8bcbc', fontSize: 12 }}>{producto.categoria}</span>
                  </button>
                ))}
              </div>
            ) : null}
            {productoSeleccionadoId ? (
              <button type="button" onClick={handleQuitarFiltro} style={quitarFiltroButtonStyle}>
                ✕ Quitar filtro
              </button>
            ) : null}
          </div>

          {productosVisibles.length === 0 ? (
            <div style={emptyStyle}>No hay platos vendidos en este rango de fechas.</div>
          ) : (
            <div style={seccionesWrapStyle}>
              {productosVisibles.map((producto) => (
                <article key={producto.producto_id} style={seccionCardStyle}>
                  <div style={seccionHeaderStyle}>
                    <span style={seccionNombreStyle}>{producto.nombre}</span>
                    <span style={seccionCategoriaStyle}>— {producto.categoria}</span>
                    {producto.tiene_estimado ? (
                      <span style={estimadoBadgeStyle} title="Al menos una venta de este plato no tiene costo histórico guardado; se usó el costo actual de la receta como estimación para esa venta puntual.">
                        tiene costo estimado
                      </span>
                    ) : null}
                  </div>
                  <div style={tableWrapStyle}>
                    <div style={tableStyle}>
                      <div style={headStyle}>Cantidad</div>
                      <div style={headStyle}>Fecha/hora</div>
                      <div style={headStyle}>Pedido</div>
                      <div style={headStyle}>Nota de entrega</div>
                      <div style={headStyle}>Ingreso</div>
                      <div style={headStyle}>Costo</div>
                      <div style={headStyle}>Ganancia</div>
                      <div style={headStyle}>%</div>
                      {producto.filas.map((fila) => (
                        <FilaVenta key={fila.detalle_id} fila={fila} />
                      ))}
                      <div style={totalCellStyle}>Total: {producto.num_ventas} línea{producto.num_ventas === 1 ? '' : 's'}</div>
                      <div style={totalCellStyle} />
                      <div style={totalCellStyle} />
                      <div style={totalCellStyle} />
                      <div style={totalCellStyle}>${formatMonto(producto.ingreso_total)}</div>
                      <div style={totalCellStyle}>${formatMonto(producto.costo_total)}</div>
                      <div style={totalCellStyle}>${formatMonto(producto.ganancia_monto)}</div>
                      <div style={totalCellStyle}>{formatMonto(producto.ganancia_pct)}%</div>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          )}

          <div style={summaryStyle}>
            {data.total_productos_distintos} producto(s) con movimiento · {data.total_lineas} venta(s) en total ·
            {' '}ingreso ${formatMonto(totales?.ingreso_total)} · costo ${formatMonto(totales?.costo_total)} ·
            {' '}ganancia ${formatMonto(totales?.ganancia_monto)} ({formatMonto(totales?.ganancia_pct)}%)
          </div>
        </section>
      ) : null}
    </section>
  );
}

function FilaVenta({ fila }) {
  const cantidadTexto = fila.peso_gramos !== null
    ? `${formatMonto(fila.peso_gramos)} g`
    : `${fila.cantidad} u.`;
  const gananciaColor = Number(fila.ganancia_monto) >= 0 ? '#8fffb0' : '#ff9d9d';

  return (
    <>
      <div style={cellStyle}>{cantidadTexto}</div>
      <div style={cellStyle}>{formatFechaHora(fila.fecha_hora)}</div>
      <div style={cellStyle}>#{fila.pedido_id}</div>
      <div style={cellStyle}>{fila.nota_entrega_codigo || '—'}</div>
      <div style={cellStyle}>${formatMonto(fila.ingreso)}</div>
      <div style={cellStyle}>
        ${formatMonto(fila.costo)}
        {fila.costo_estimado ? (
          <span style={estimadoBadgeInlineStyle} title="Esta venta no tiene costo histórico guardado; se muestra el costo actual de la receta como estimación.">
            estimado
          </span>
        ) : null}
      </div>
      <div style={{ ...cellStyle, color: gananciaColor, fontWeight: 700 }}>${formatMonto(fila.ganancia_monto)}</div>
      <div style={{ ...cellStyle, color: gananciaColor, fontWeight: 700 }}>{formatMonto(fila.ganancia_pct)}%</div>
    </>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const titleStyle = (isMobile) => ({ margin: 0, color: '#fff', fontSize: isMobile ? 28 : 34 });
const filtersRowStyle = (isMobile) => ({
  display: 'flex',
  gap: 14,
  flexWrap: 'wrap',
  alignItems: isMobile ? 'stretch' : 'flex-end',
  flexDirection: isMobile ? 'column' : 'row',
});
const dateLabelStyle = { display: 'flex', flexDirection: 'column', gap: 6, color: '#f2e6e6', fontSize: 13, fontWeight: 700 };
const dateInputStyle = { borderRadius: 12, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '10px 12px', color: '#fff' };
const presetsWrapStyle = { display: 'flex', gap: 8, flexWrap: 'wrap' };
const presetButtonStyle = { border: '1px solid rgba(255,255,255,0.16)', borderRadius: 999, padding: '9px 14px', background: 'rgba(255,255,255,0.05)', color: '#fff', fontSize: 13, fontWeight: 700, cursor: 'pointer' };
const panelStyle = { display: 'grid', gap: 14, padding: 18, borderRadius: 20, border: '1px solid rgba(255,255,255,0.1)', background: 'linear-gradient(180deg, rgba(20,10,10,0.95) 0%, rgba(8,8,8,0.98) 100%)' };
const sectionTitleStyle = { color: '#fff', fontSize: 19, fontWeight: 700 };
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(255,255,255,0.12)', color: '#c8bbbb' };
const noticeStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid rgba(255,145,145,0.22)', background: 'rgba(255,98,98,0.12)', color: '#ffd8d8' };
const printButtonStyle = { border: '1px solid rgba(255,255,255,0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(255,255,255,0.04)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };
const summaryStyle = { color: '#c8bbbb', fontSize: 13 };

const fieldStyle = { display: 'grid', gap: 6 };
const searchInputStyle = { width: '100%', boxSizing: 'border-box', borderRadius: 12, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '10px 12px', color: '#fff', fontSize: 14 };
const suggestionsPanelStyle = { position: 'absolute', top: '100%', left: 0, right: 0, marginTop: 6, zIndex: 5, borderRadius: 12, border: '1px solid rgba(255,255,255,0.14)', background: 'rgba(10, 8, 8, 0.98)', boxShadow: '0 12px 30px rgba(0,0,0,0.4)', padding: 8, display: 'grid', gap: 4, maxHeight: 260, overflowY: 'auto' };
const suggestionRowStyle = { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 10, padding: '8px 10px', background: 'rgba(255,255,255,0.04)', cursor: 'pointer', textAlign: 'left' };
const quitarFiltroButtonStyle = { marginTop: 8, border: '1px solid rgba(255,126,126,0.4)', borderRadius: 999, padding: '6px 14px', background: 'rgba(145,33,33,0.25)', color: '#ffd3d3', fontWeight: 700, cursor: 'pointer', fontSize: 12.5, width: 'fit-content' };

const seccionesWrapStyle = { display: 'grid', gap: 18 };
const seccionCardStyle = { display: 'grid', gap: 10, padding: 14, borderRadius: 16, border: '1px solid rgba(255,255,255,0.08)', background: 'rgba(255,255,255,0.02)' };
const seccionHeaderStyle = { display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' };
const seccionNombreStyle = { color: '#ffb0b0', fontSize: 16, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.03em' };
const seccionCategoriaStyle = { color: '#c8bbbb', fontSize: 13 };
const estimadoBadgeStyle = {
  padding: '2px 8px',
  borderRadius: 999,
  background: 'rgba(255, 200, 120, 0.16)',
  color: '#ffcf7d',
  fontSize: 10.5,
  fontWeight: 800,
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
};
const estimadoBadgeInlineStyle = { ...estimadoBadgeStyle, marginLeft: 6, fontSize: 9.5, padding: '1px 6px' };

const tableWrapStyle = { overflowX: 'auto' };
const tableStyle = { display: 'grid', gridTemplateColumns: 'minmax(90px,0.7fr) minmax(130px,0.9fr) minmax(70px,0.5fr) minmax(120px,0.9fr) minmax(90px,0.7fr) minmax(120px,0.9fr) minmax(90px,0.7fr) minmax(70px,0.5fr)', gap: '4px 10px', alignItems: 'center', minWidth: 900 };
const headStyle = { color: '#f0b4b4', fontSize: 11, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em', padding: '4px 2px', borderBottom: '1px solid rgba(255,255,255,0.1)' };
const cellStyle = { color: '#f2e6e6', fontSize: 13, padding: '5px 2px', borderBottom: '1px solid rgba(255,255,255,0.05)' };
const totalCellStyle = { color: '#8fffb0', fontSize: 13, fontWeight: 800, padding: '8px 2px', borderTop: '2px solid rgba(143,255,176,0.35)', background: 'rgba(70,200,120,0.06)' };

export default AnalystMargenGananciaPage;
