import { useCallback, useEffect, useMemo, useState } from 'react';
import { RangoFechas } from './FiltroFechas';

function toIso(date) {
  const offset = date.getTimezoneOffset();
  const local = new Date(date.getTime() - offset * 60000);
  return local.toISOString().slice(0, 10);
}

function todayIso() {
  return toIso(new Date());
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

function AnalystMovimientoProductosPage({ isMobile, onBack }) {
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
        `/api/admin/reportes/movimiento-productos/?desde=${desdeConsultado}&hasta=${hastaConsultado}`,
        { credentials: 'include', cache: 'no-store' },
      );
      const json = await response.json();
      if (!response.ok || !json.ok) {
        throw new Error(json.message || 'No se pudo cargar el reporte de movimiento de productos.');
      }
      setData(json);
    } catch (requestError) {
      setError(requestError.message || 'No se pudo cargar el reporte de movimiento de productos.');
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
        <h2 style={titleStyle(isMobile)}>Movimiento de productos</h2>
      </div>

      <RangoFechas
        desde={desde}
        hasta={hasta}
        onChange={(rango) => {
          setDesde(rango.desde);
          setHasta(rango.hasta);
        }}
      />

      {loading ? <div style={emptyStyle}>Cargando reporte...</div> : null}
      {!loading && error ? <div style={noticeStyle}>{error}</div> : null}

      {!loading && !error && data ? (
        <section style={panelStyle}>
          <div style={sectionTitleStyle}>
            {desde === hasta ? `Movimiento del ${desde}` : `Movimiento del ${desde} al ${hasta}`}
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
                    <span style={{ color: 'var(--vg-text-strong)', fontWeight: 600 }}>{producto.nombre}</span>
                    <span style={{ color: 'var(--vg-f-e8bcbc)', fontSize: 12 }}>{producto.categoria}</span>
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
            <div style={emptyStyle}>No hay productos con movimiento para este filtro.</div>
          ) : (
            <div style={seccionesWrapStyle}>
              {productosVisibles.map((producto) => (
                <article key={producto.producto_id} style={seccionCardStyle}>
                  <div style={seccionHeaderStyle}>
                    <span style={seccionNombreStyle}>{producto.nombre}</span>
                    <span style={seccionCategoriaStyle}>— {producto.categoria}</span>
                  </div>
                  <div style={tableWrapStyle}>
                    <div style={tableStyle}>
                      <div style={headStyle}>Cantidad</div>
                      <div style={headStyle}>Fecha/hora</div>
                      <div style={headStyle}>Pedido</div>
                      <div style={headStyle}>Nota de entrega</div>
                      {producto.filas.map((fila) => (
                        <FilaVenta key={fila.detalle_id} fila={fila} unidad={producto.unidad} />
                      ))}
                      <div style={totalCellPrimaryStyle}>
                        {formatMonto(producto.total_cantidad)} {producto.unidad === 'kg' ? 'kg' : 'u.'}
                      </div>
                      <div style={totalCellStyle}>Total: {producto.num_ventas} línea{producto.num_ventas === 1 ? '' : 's'}</div>
                      <div style={totalCellStyle} />
                      <div style={totalCellStyle} />
                    </div>
                  </div>
                </article>
              ))}
            </div>
          )}

          <div style={summaryStyle}>
            {data.total_productos_distintos} producto(s) con movimiento · {data.total_lineas} venta(s) en total
            {Number(data.total_unidades_vendidas) > 0 ? ` · ${formatMonto(data.total_unidades_vendidas)} unidades vendidas` : ''}
            {Number(data.total_kg_vendidos) > 0 ? ` · ${formatMonto(data.total_kg_vendidos)} kg vendidos` : ''}
          </div>
        </section>
      ) : null}
    </section>
  );
}

function FilaVenta({ fila, unidad }) {
  const cantidadTexto = unidad === 'kg'
    ? `${formatMonto(fila.peso_gramos)} g`
    : `${fila.cantidad} u.`;

  return (
    <>
      <div style={cellStyle}>{cantidadTexto}</div>
      <div style={cellStyle}>{formatFechaHora(fila.fecha_hora)}</div>
      <div style={cellStyle}>#{fila.pedido_id}</div>
      <div style={cellStyle}>{fila.nota_entrega_codigo || '—'}</div>
    </>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const titleStyle = (isMobile) => ({ margin: 0, color: 'var(--vg-text-strong)', fontSize: isMobile ? 28 : 34 });
const panelStyle = { display: 'grid', gap: 14, padding: 18, borderRadius: 20, border: '1px solid rgba(var(--vg-ink), 0.1)', background: 'linear-gradient(180deg, var(--vg-bg-card) 0%, var(--vg-s-080808-a980) 100%)' };
const sectionTitleStyle = { color: 'var(--vg-text-strong)', fontSize: 19, fontWeight: 700 };
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(var(--vg-ink), 0.12)', color: 'var(--vg-f-c8bbbb)' };
const noticeStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid var(--vg-f-ff9191-a220)', background: 'rgba(255,98,98,0.12)', color: 'var(--vg-f-ffd8d8)' };
const printButtonStyle = { border: '1px solid rgba(var(--vg-ink), 0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(var(--vg-ink), 0.04)', color: 'var(--vg-text-strong)', fontWeight: 700, cursor: 'pointer' };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };
const summaryStyle = { color: 'var(--vg-f-c8bbbb)', fontSize: 13 };

const fieldStyle = { display: 'grid', gap: 6 };
const searchInputStyle = { width: '100%', boxSizing: 'border-box', borderRadius: 12, border: '1px solid rgba(var(--vg-ink), 0.14)', background: 'var(--vg-s-161010)', padding: '10px 12px', color: 'var(--vg-text-strong)', fontSize: 14 };
const suggestionsPanelStyle = { position: 'absolute', top: '100%', left: 0, right: 0, marginTop: 6, zIndex: 5, borderRadius: 12, border: '1px solid rgba(var(--vg-ink), 0.14)', background: 'var(--vg-s-0a0808-a980)', boxShadow: '0 12px 30px rgba(0, 0, 0, calc(0.4 * var(--vg-shadow-k)))', padding: 8, display: 'grid', gap: 4, maxHeight: 260, overflowY: 'auto' };
const suggestionRowStyle = { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, border: '1px solid rgba(var(--vg-ink), 0.08)', borderRadius: 10, padding: '8px 10px', background: 'rgba(var(--vg-ink), 0.04)', cursor: 'pointer', textAlign: 'left' };
const quitarFiltroButtonStyle = { marginTop: 8, border: '1px solid var(--vg-f-ff7e7e-a400)', borderRadius: 999, padding: '6px 14px', background: 'rgba(145,33,33,0.25)', color: 'var(--vg-f-ffd3d3)', fontWeight: 700, cursor: 'pointer', fontSize: 12.5, width: 'fit-content' };

const seccionesWrapStyle = { display: 'grid', gap: 18 };
const seccionCardStyle = { display: 'grid', gap: 10, padding: 14, borderRadius: 16, border: '1px solid rgba(var(--vg-ink), 0.08)', background: 'rgba(var(--vg-ink), 0.02)' };
const seccionHeaderStyle = { display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' };
const seccionNombreStyle = { color: 'var(--vg-f-ffb0b0)', fontSize: 16, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.03em' };
const seccionCategoriaStyle = { color: 'var(--vg-f-c8bbbb)', fontSize: 13 };

const tableWrapStyle = { overflowX: 'auto' };
const tableStyle = { display: 'grid', gridTemplateColumns: 'minmax(100px,0.8fr) minmax(140px,1fr) minmax(80px,0.6fr) minmax(140px,1fr)', gap: '4px 12px', alignItems: 'center', minWidth: 560 };
const headStyle = { color: 'var(--vg-f-f0b4b4)', fontSize: 11, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em', padding: '4px 2px', borderBottom: '1px solid rgba(var(--vg-ink), 0.1)' };
const cellStyle = { color: 'var(--vg-f-f2e6e6)', fontSize: 13, padding: '5px 2px', borderBottom: '1px solid rgba(var(--vg-ink), 0.05)' };
const totalCellStyle = { color: 'var(--vg-f-8fffb0)', fontSize: 13, fontWeight: 800, padding: '8px 2px', borderTop: '2px solid var(--vg-f-8fffb0-a350)', background: 'rgba(70,200,120,0.06)' };
const totalCellPrimaryStyle = { ...totalCellStyle };

export default AnalystMovimientoProductosPage;
