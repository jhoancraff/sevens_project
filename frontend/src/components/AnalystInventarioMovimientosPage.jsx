import { useCallback, useEffect, useState } from 'react';
import BotonDescargarPdf from './BotonDescargarPdf';
import Toast from './Toast';
import useToast from '../hooks/useToast';

function isoLocal(fecha) {
  const local = new Date(fecha.getTime() - fecha.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

function inicioDeMes() {
  const hoy = new Date();
  return isoLocal(new Date(hoy.getFullYear(), hoy.getMonth(), 1));
}

function numero(valor) {
  const n = Number(valor);
  return Number.isFinite(n) ? n.toLocaleString('es-VE', { maximumFractionDigits: 2 }) : valor;
}

const ORIGENES = [
  { value: 'todo', label: 'Ingredientes y utensilios' },
  { value: 'utensilios', label: 'Solo utensilios y equipos' },
  { value: 'ingredientes', label: 'Solo ingredientes' },
];
const TIPOS = [
  { value: '', label: 'Todos los movimientos' },
  { value: 'entrada', label: 'Entradas' },
  { value: 'salida', label: 'Salidas (ventas, reposición)' },
  { value: 'entrega', label: 'Entregas a empleados' },
  { value: 'baja', label: 'Bajas' },
  { value: 'ajuste', label: 'Ajustes' },
];

// «Movimientos del inventario»: todo lo que entró, salió o se ajustó, de ingredientes y de utensilios,
// en el rango de fechas que se elige. El resumen explica el stock actual de cada artículo
// (inicial + entradas − salidas − bajas ± ajustes = final) y el detalle lista cada movimiento.
function AnalystInventarioMovimientosPage({ isMobile, onBack }) {
  const { toast, showError, hideToast } = useToast();
  const [filtros, setFiltros] = useState({
    desde: inicioDeMes(), hasta: isoLocal(new Date()), origen: 'todo', tipo: '', q: '', receptor: '', pagina: 1,
  });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const cargar = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams(Object.entries(filtros).filter(([, valor]) => valor !== '' && valor !== null));
      const response = await fetch(`/api/admin/inventario-movimientos/?${params.toString()}`, { credentials: 'include', cache: 'no-store' });
      const json = await response.json().catch(() => ({}));
      if (!response.ok || !json.ok) {
        throw new Error(json.message || 'No se pudieron cargar los movimientos.');
      }
      setData(json);
    } catch (error) {
      showError(error.message);
      setData(null);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtros]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  // Cambiar un filtro vuelve a la primera página.
  const cambiar = (campo, valor) => setFiltros((actual) => ({ ...actual, [campo]: valor, pagina: 1 }));
  const rangoValido = filtros.desde && filtros.hasta && filtros.desde <= filtros.hasta;
  const { pagina, ...filtrosPdf } = filtros;

  return (
    <section style={containerStyle(isMobile)}>
      <button type="button" onClick={onBack} style={backButtonStyle}>← Volver</button>

      <div style={headerRowStyle(isMobile)}>
        <div>
          <h2 style={titleStyle(isMobile)}>Movimientos del inventario</h2>
          <p style={subtitleStyle}>
            Qué entró, qué salió y qué se ajustó, de ingredientes y de utensilios y equipos. El resumen explica el stock actual
            de cada artículo: lo que había al inicio, más las entradas, menos las salidas y bajas, más o menos los ajustes.
          </p>
        </div>
        <BotonDescargarPdf url="/api/admin/reportes/inventario-movimientos-pdf/" params={filtrosPdf} onError={showError}>
          Descargar PDF
        </BotonDescargarPdf>
      </div>

      <Toast toast={toast} onClose={hideToast} />

      <section style={panelStyle}>
        <div style={filtrosStyle(isMobile)}>
          <label style={fieldStyle}>
            <span>Desde</span>
            <input type="date" value={filtros.desde} onChange={(e) => cambiar('desde', e.target.value)} style={inputStyle} />
          </label>
          <label style={fieldStyle}>
            <span>Hasta</span>
            <input type="date" value={filtros.hasta} onChange={(e) => cambiar('hasta', e.target.value)} style={inputStyle} />
          </label>
          <label style={fieldStyle}>
            <span>Qué ver</span>
            <select value={filtros.origen} onChange={(e) => cambiar('origen', e.target.value)} style={inputStyle} className="admin-dark-select">
              {ORIGENES.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </label>
          <label style={fieldStyle}>
            <span>Movimiento</span>
            <select value={filtros.tipo} onChange={(e) => cambiar('tipo', e.target.value)} style={inputStyle} className="admin-dark-select">
              {TIPOS.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </label>
          <label style={fieldStyle}>
            <span>Artículo</span>
            <input value={filtros.q} onChange={(e) => cambiar('q', e.target.value)} placeholder="Nombre del artículo" style={inputStyle} />
          </label>
          <label style={fieldStyle}>
            <span>Recibió (entregas)</span>
            <input value={filtros.receptor} onChange={(e) => cambiar('receptor', e.target.value)} placeholder="Nombre del empleado" style={inputStyle} />
          </label>
        </div>
        {!rangoValido ? <div style={noticeStyle}>«Desde» no puede ser posterior a «Hasta».</div> : null}
      </section>

      {loading ? <div style={emptyStyle}>Cargando...</div> : null}

      {!loading && data ? (
        <>
          <section style={panelStyle}>
            <div style={sectionTitleStyle}>
              Resumen por artículo <span style={mutedStyle}>({data.resumen.length} con movimientos)</span>
            </div>
            {data.resumen.length === 0 ? <div style={emptyStyle}>No hubo movimientos en este rango.</div> : (
              <div style={tableWrapStyle}>
                <div style={tablaResumenStyle}>
                  <div style={headStyle}>Artículo</div>
                  <div style={{ ...headStyle, textAlign: 'right' }}>Inicial</div>
                  <div style={{ ...headStyle, textAlign: 'right' }}>Entradas</div>
                  <div style={{ ...headStyle, textAlign: 'right' }}>Salidas / entregas</div>
                  <div style={{ ...headStyle, textAlign: 'right' }}>Bajas</div>
                  <div style={{ ...headStyle, textAlign: 'right' }}>Ajustes</div>
                  <div style={{ ...headStyle, textAlign: 'right' }}>Final</div>
                  <div style={{ ...headStyle, textAlign: 'right' }}>Stock actual</div>
                  {data.resumen.map((fila) => (
                    <div key={`${fila.origen}-${fila.id}`} style={{ display: 'contents' }}>
                      <div style={cellStyle}>
                        <strong>{fila.nombre}</strong>
                        <span style={mutedStyle}>
                          {fila.origen === 'ingrediente' ? `Ingrediente · ${fila.unidad}` : 'Utensilio'}
                          {fila.categoria ? ` · ${fila.categoria}` : ''}
                        </span>
                      </div>
                      <div style={numeroStyle}>{numero(fila.inicial)}</div>
                      <div style={{ ...numeroStyle, color: Number(fila.entradas) > 0 ? 'var(--vg-f-8fffb0)' : undefined }}>
                        {Number(fila.entradas) > 0 ? `+${numero(fila.entradas)}` : '0'}
                      </div>
                      <div style={{ ...numeroStyle, color: Number(fila.salidas) > 0 ? 'var(--vg-f-ffb0b0)' : undefined }}>
                        {Number(fila.salidas) > 0 ? `−${numero(fila.salidas)}` : '0'}
                      </div>
                      <div style={{ ...numeroStyle, color: Number(fila.bajas) > 0 ? 'var(--vg-f-ffb0b0)' : undefined }}>
                        {Number(fila.bajas) > 0 ? `−${numero(fila.bajas)}` : '0'}
                      </div>
                      <div style={numeroStyle}>{Number(fila.ajustes) > 0 ? `+${numero(fila.ajustes)}` : numero(fila.ajustes)}</div>
                      <div style={{ ...numeroStyle, fontWeight: 800 }}>{numero(fila.final)}</div>
                      <div style={numeroStyle}>{numero(fila.actual)}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
            <div style={mutedStyle}>
              La existencia se calcula hacia atrás desde el stock actual de cada artículo. Un cambio de stock hecho a mano
              (editando el ingrediente) no deja movimiento y por eso no aparece aquí.
            </div>
          </section>

          <section style={panelStyle}>
            <div style={sectionTitleStyle}>
              Detalle de movimientos <span style={mutedStyle}>({data.total_movimientos})</span>
            </div>
            {data.movimientos.length === 0 ? <div style={emptyStyle}>No hubo movimientos en este rango.</div> : (
              <div style={tableWrapStyle}>
                <div style={tablaDetalleStyle}>
                  <div style={headStyle}>Fecha</div>
                  <div style={headStyle}>Artículo</div>
                  <div style={headStyle}>Movimiento</div>
                  <div style={{ ...headStyle, textAlign: 'right' }}>Cantidad</div>
                  <div style={headStyle}>Motivo</div>
                  <div style={headStyle}>Recibió</div>
                  <div style={headStyle}>Registró</div>
                  <div style={headStyle}>Comprobante</div>
                  {data.movimientos.map((mov) => (
                    <div key={`${mov.origen}-${mov.movimiento_id}`} style={{ display: 'contents' }}>
                      <div style={cellStyle}>{new Date(mov.fecha).toLocaleString('es-VE', { dateStyle: 'short', timeStyle: 'short' })}</div>
                      <div style={cellStyle}>
                        <strong>{mov.articulo}</strong>
                        <span style={mutedStyle}>{mov.origen === 'ingrediente' ? mov.unidad : 'Utensilio'}</span>
                      </div>
                      <div style={cellStyle}>{mov.tipo_label}</div>
                      <div style={{ ...numeroStyle, fontWeight: 800, color: Number(mov.delta) < 0 ? 'var(--vg-f-ffb0b0)' : 'var(--vg-f-8fffb0)' }}>
                        {Number(mov.delta) > 0 ? `+${numero(mov.delta)}` : numero(mov.delta)}
                      </div>
                      <div style={cellStyle}>{mov.motivo || '—'}</div>
                      <div style={cellStyle}>{mov.receptor || '—'}</div>
                      <div style={cellStyle}>{mov.registrado_por || '—'}</div>
                      <div style={cellStyle}>
                        {mov.comprobante ? (
                          <BotonDescargarPdf url={`/api/admin/activos/entregas/${mov.movimiento_id}/comprobante-pdf/`} onError={showError}>
                            {mov.comprobante}
                          </BotonDescargarPdf>
                        ) : '—'}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {data.paginas > 1 ? (
              <div style={paginacionStyle}>
                <button
                  type="button"
                  style={secondaryButtonStyle}
                  disabled={filtros.pagina <= 1}
                  onClick={() => setFiltros((actual) => ({ ...actual, pagina: actual.pagina - 1 }))}
                >
                  ← Anterior
                </button>
                <span style={mutedStyle}>Página {data.pagina} de {data.paginas}</span>
                <button
                  type="button"
                  style={secondaryButtonStyle}
                  disabled={filtros.pagina >= data.paginas}
                  onClick={() => setFiltros((actual) => ({ ...actual, pagina: actual.pagina + 1 }))}
                >
                  Siguiente →
                </button>
              </div>
            ) : null}
          </section>
        </>
      ) : null}
    </section>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const headerRowStyle = (isMobile) => ({ display: 'flex', justifyContent: 'space-between', alignItems: isMobile ? 'flex-start' : 'center', flexDirection: isMobile ? 'column' : 'row', gap: 12 });
const titleStyle = (isMobile) => ({ margin: 0, color: 'var(--vg-text-strong)', fontSize: isMobile ? 28 : 34 });
const subtitleStyle = { margin: '8px 0 0', color: 'var(--vg-f-d2c3c3)', lineHeight: 1.6, maxWidth: 760 };
const panelStyle = { display: 'grid', gap: 14, padding: 18, borderRadius: 20, border: '1px solid rgba(var(--vg-ink), 0.1)', background: 'linear-gradient(180deg, var(--vg-bg-card) 0%, var(--vg-s-080808-a980) 100%)' };
const sectionTitleStyle = { color: 'var(--vg-text-strong)', fontSize: 19, fontWeight: 700 };
const filtrosStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(6, minmax(0, 1fr))', gap: 10 });
const fieldStyle = { display: 'grid', gap: 6, color: 'var(--vg-f-f2e6e6)', fontSize: 12.5, fontWeight: 700 };
const inputStyle = { borderRadius: 12, border: '1px solid rgba(var(--vg-ink), 0.14)', background: 'var(--vg-s-161010)', padding: '10px 12px', color: 'var(--vg-text-strong)', width: '100%', boxSizing: 'border-box' };
const noticeStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid var(--vg-f-ff9191-a220)', background: 'rgba(255,98,98,0.12)', color: 'var(--vg-f-ffd8d8)' };
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(var(--vg-ink), 0.12)', color: 'var(--vg-f-c8bbbb)' };
const mutedStyle = { color: 'var(--vg-f-a89999)', fontSize: 12.5, fontWeight: 400, display: 'block' };
const tableWrapStyle = { overflowX: 'auto' };
const tablaResumenStyle = { display: 'grid', gridTemplateColumns: 'minmax(220px,1.6fr) repeat(7, minmax(88px,0.6fr))', minWidth: 960, border: '1px solid rgba(var(--vg-ink), 0.08)', borderRadius: 14, overflow: 'hidden' };
const tablaDetalleStyle = { display: 'grid', gridTemplateColumns: 'minmax(120px,0.8fr) minmax(180px,1.2fr) minmax(130px,0.8fr) minmax(90px,0.5fr) minmax(200px,1.4fr) minmax(110px,0.7fr) minmax(100px,0.6fr) minmax(120px,0.7fr)', minWidth: 1100, border: '1px solid rgba(var(--vg-ink), 0.08)', borderRadius: 14, overflow: 'hidden' };
const headStyle = { padding: '12px 14px', background: 'rgba(var(--vg-ink), 0.06)', color: 'var(--vg-f-ffb0b0)', fontSize: 12, letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 800 };
const cellStyle = { padding: '12px 14px', borderTop: '1px solid rgba(var(--vg-ink), 0.08)', color: 'var(--vg-f-f2e6e6)', display: 'grid', alignContent: 'center', gap: 2 };
const numeroStyle = { ...cellStyle, textAlign: 'right' };
const paginacionStyle = { display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 14 };
const secondaryButtonStyle = { border: '1px solid rgba(var(--vg-ink), 0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(var(--vg-ink), 0.04)', color: 'var(--vg-text-strong)', fontWeight: 700, cursor: 'pointer' };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };

export default AnalystInventarioMovimientosPage;
