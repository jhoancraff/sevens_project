import { useCallback, useEffect, useState } from 'react';
import BotonDescargarPdf from './BotonDescargarPdf';
import Toast from './Toast';
import useToast from '../hooks/useToast';

const TIPOS = [
  { value: 'todo', label: 'Todo junto' },
  { value: 'ingredientes', label: 'Solo ingredientes' },
  { value: 'utensilios', label: 'Solo utensilios y equipos' },
];

function dinero(valor) {
  return Number(valor || 0).toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// «Todo el inventario»: ingredientes y utensilios en una sola pantalla, juntos o separados. Solo
// lectura (se edita desde cada sección). Los valores NO se mezclan: cada tipo lleva su subtotal.
function AnalystInventarioGeneralPage({ isMobile, onBack }) {
  const { toast, showError, hideToast } = useToast();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filtros, setFiltros] = useState({ tipo: 'todo', categoria: '', q: '' });

  const cargar = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams(Object.entries(filtros).filter(([, valor]) => valor));
      const response = await fetch(`/api/admin/inventario-general/?${params.toString()}`, { credentials: 'include', cache: 'no-store' });
      const json = await response.json().catch(() => ({}));
      if (!response.ok || !json.ok) {
        throw new Error(json.message || 'No se pudo cargar el inventario.');
      }
      setData(json);
    } catch (error) {
      showError(error.message);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtros]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const cambiar = (campo, valor) => setFiltros((actual) => ({ ...actual, [campo]: valor }));
  const verIng = filtros.tipo !== 'utensilios';
  const verArt = filtros.tipo !== 'ingredientes';
  const resumen = data?.resumen;

  return (
    <section style={containerStyle(isMobile)}>
      <button type="button" onClick={onBack} style={backButtonStyle}>← Volver</button>

      <div style={headerRowStyle(isMobile)}>
        <div>
          <h2 style={titleStyle(isMobile)}>Todo el inventario</h2>
          <p style={subtitleStyle}>
            Ingredientes y utensilios y equipos, juntos o separados. Cada tipo suma aparte: el valor de los ingredientes
            (costo de receta) no se mezcla con el de compra de los utensilios.
          </p>
        </div>
        <BotonDescargarPdf url="/api/admin/reportes/inventario-general-pdf/" params={filtros} onError={showError}>
          Descargar PDF
        </BotonDescargarPdf>
      </div>

      <Toast toast={toast} onClose={hideToast} />

      <section style={panelStyle}>
        <div style={filtrosStyle(isMobile)}>
          <select value={filtros.tipo} onChange={(e) => cambiar('tipo', e.target.value)} style={inputStyle} className="admin-dark-select">
            {TIPOS.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
          <select value={filtros.categoria} onChange={(e) => cambiar('categoria', e.target.value)} style={inputStyle} className="admin-dark-select">
            <option value="">Todas las categorías</option>
            <option value="sin">Sin categoría</option>
            {data && data.categorias_ingredientes.length > 0 ? (
              <optgroup label="Categorías de ingredientes">
                {data.categorias_ingredientes.map((c) => <option key={`i${c.id}`} value={`i:${c.id}`}>{c.nombre}</option>)}
              </optgroup>
            ) : null}
            {data && data.categorias_utensilios.length > 0 ? (
              <optgroup label="Categorías de utensilios">
                {data.categorias_utensilios.map((c) => <option key={`a${c.id}`} value={`a:${c.id}`}>{c.nombre}</option>)}
              </optgroup>
            ) : null}
          </select>
          <input value={filtros.q} onChange={(e) => cambiar('q', e.target.value)} placeholder="Buscar por nombre, categoría o ubicación" style={inputStyle} />
        </div>

        {resumen ? (
          <div style={resumenStyle}>
            {verIng ? <span>Ingredientes: <strong>{resumen.ingredientes}</strong> · ${dinero(resumen.valor_ingredientes)}</span> : null}
            {verArt ? <span>Utensilios: <strong>{resumen.utensilios}</strong> · ${dinero(resumen.valor_utensilios)} (valor de compra)</span> : null}
            {verIng && verArt ? (
              <strong>Patrimonio total: ${dinero(Number(resumen.valor_ingredientes) + Number(resumen.valor_utensilios))}</strong>
            ) : null}
          </div>
        ) : null}
      </section>

      {loading ? <div style={emptyStyle}>Cargando...</div> : null}

      {!loading && data && verIng ? (
        <section style={panelStyle}>
          <div style={sectionTitleStyle}>Ingredientes <span style={mutedStyle}>({data.ingredientes.length})</span></div>
          {data.ingredientes.length === 0 ? <div style={emptyStyle}>No hay ingredientes con ese filtro.</div> : (
            <div style={tableWrapStyle}>
              <div style={tablaIngStyle}>
                <div style={headStyle}>Ingrediente</div>
                <div style={headStyle}>Categoría</div>
                <div style={{ ...headStyle, textAlign: 'right' }}>Stock</div>
                <div style={{ ...headStyle, textAlign: 'right' }}>Valor</div>
                {data.ingredientes.map((fila) => (
                  <div key={`i-${fila.id}`} style={{ display: 'contents' }}>
                    <div style={cellStyle}><strong>{fila.nombre}</strong></div>
                    <div style={cellStyle}>{fila.categoria || '—'}</div>
                    <div style={{ ...cellStyle, textAlign: 'right' }}>{dinero(fila.cantidad)} {fila.unidad}</div>
                    <div style={{ ...cellStyle, textAlign: 'right' }}>${dinero(fila.valor_total)}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
      ) : null}

      {!loading && data && verArt ? (
        <section style={panelStyle}>
          <div style={sectionTitleStyle}>Utensilios y equipos <span style={mutedStyle}>({data.utensilios.length})</span></div>
          {data.utensilios.length === 0 ? <div style={emptyStyle}>No hay utensilios con ese filtro.</div> : (
            <div style={tableWrapStyle}>
              <div style={tablaArtStyle}>
                <div style={headStyle}>Artículo</div>
                <div style={headStyle}>Categoría</div>
                <div style={headStyle}>Ubicación</div>
                <div style={headStyle}>Estado</div>
                <div style={{ ...headStyle, textAlign: 'right' }}>Cantidad</div>
                <div style={{ ...headStyle, textAlign: 'right' }}>Valor</div>
                {data.utensilios.map((fila) => (
                  <div key={`a-${fila.id}`} style={{ display: 'contents' }}>
                    <div style={cellStyle}><strong>{fila.nombre}</strong><span style={mutedStyle}>{fila.tipo}</span></div>
                    <div style={cellStyle}>{fila.categoria || '—'}</div>
                    <div style={cellStyle}>{fila.ubicacion || '—'}</div>
                    <div style={cellStyle}>{fila.estado}</div>
                    <div style={{ ...cellStyle, textAlign: 'right' }}>{fila.cantidad}</div>
                    <div style={{ ...cellStyle, textAlign: 'right' }}>${dinero(fila.valor_total)}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
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
const filtrosStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, minmax(0, 1fr))', gap: 10 });
const resumenStyle = { display: 'flex', gap: 18, flexWrap: 'wrap', color: 'var(--vg-f-f2e6e6)', fontSize: 14 };
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(var(--vg-ink), 0.12)', color: 'var(--vg-f-c8bbbb)' };
const mutedStyle = { color: 'var(--vg-f-a89999)', fontSize: 12.5, fontWeight: 400, display: 'block' };
const inputStyle = { borderRadius: 12, border: '1px solid rgba(var(--vg-ink), 0.14)', background: 'var(--vg-s-161010)', padding: '10px 12px', color: 'var(--vg-text-strong)', width: '100%', boxSizing: 'border-box' };
const tableWrapStyle = { overflowX: 'auto' };
const tablaIngStyle = { display: 'grid', gridTemplateColumns: 'minmax(220px,1.4fr) minmax(150px,1fr) minmax(140px,0.8fr) minmax(120px,0.7fr)', minWidth: 700, border: '1px solid rgba(var(--vg-ink), 0.08)', borderRadius: 14, overflow: 'hidden' };
const tablaArtStyle = { display: 'grid', gridTemplateColumns: 'minmax(200px,1.3fr) minmax(130px,0.9fr) minmax(110px,0.7fr) minmax(100px,0.6fr) minmax(90px,0.5fr) minmax(110px,0.6fr)', minWidth: 760, border: '1px solid rgba(var(--vg-ink), 0.08)', borderRadius: 14, overflow: 'hidden' };
const headStyle = { padding: '12px 14px', background: 'rgba(var(--vg-ink), 0.06)', color: 'var(--vg-f-ffb0b0)', fontSize: 12, letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 800 };
const cellStyle = { padding: '12px 14px', borderTop: '1px solid rgba(var(--vg-ink), 0.08)', color: 'var(--vg-f-f2e6e6)', display: 'grid', alignContent: 'center', gap: 2 };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };

export default AnalystInventarioGeneralPage;
