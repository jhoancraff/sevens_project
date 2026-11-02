import { useCallback, useEffect, useState } from 'react';
import ConfirmModal from './ConfirmModal';
import MenuAcciones from './MenuAcciones';
import Toast from './Toast';
import useToast from '../hooks/useToast';

async function pedir(opciones) {
  const response = await fetch('/api/admin/categorias-productos/', {
    credentials: 'include',
    cache: 'no-store',
    ...opciones,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.ok) {
    throw new Error(data.message || 'No se pudo completar la operación.');
  }
  return data;
}

const textoProductos = (cantidad) => `${cantidad} ${cantidad === 1 ? 'producto' : 'productos'}`;

// Categorías del menú (Platos, Bebidas, Pizzas...): crear, editar, desactivar y eliminar.
// Desactivar una categoría la oculta de la pantalla de pedido de los meseros sin tocar sus
// productos; eliminarla solo se puede si no tiene productos.
function AnalystProductCategoriesPage({ isMobile, onBack, onViewProducts }) {
  const [categorias, setCategorias] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [nuevoNombre, setNuevoNombre] = useState('');
  const [nuevaDescripcion, setNuevaDescripcion] = useState('');
  const [edicion, setEdicion] = useState(null); // { id, nombre, descripcion }
  const { toast, showSuccess, showError, hideToast } = useToast();
  const [confirmacion, setConfirmacion] = useState(null);

  const cargar = useCallback(async () => {
    setLoading(true);
    try {
      const data = await pedir({});
      setCategorias(data.categorias || []);
    } catch (error) {
      showError(error.message);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const enviar = async (cuerpo) => {
    setSaving(true);
    try {
      const data = await pedir({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cuerpo),
      });
      if (Array.isArray(data.categorias)) {
        setCategorias(data.categorias);
      }
      showSuccess(data.message || 'Listo.');
      return true;
    } catch (error) {
      showError(error.message);
      return false;
    } finally {
      setSaving(false);
    }
  };

  // Todo guardar, actualizar, desactivar o eliminar pasa primero por un diálogo de confirmación.
  const confirmar = async () => {
    if (!confirmacion) {
      return;
    }
    const hecho = await enviar(confirmacion.cuerpo);
    if (hecho && confirmacion.alTerminar) {
      confirmacion.alTerminar();
    }
    setConfirmacion(null);
  };

  const handleCrear = (event) => {
    event.preventDefault();
    const nombre = nuevoNombre.trim();
    if (!nombre) {
      showError('Escribe el nombre de la categoría.');
      return;
    }
    setConfirmacion({
      title: 'Guardar categoría',
      message: `¿Crear la categoría «${nombre}»? Después podrás asignarle productos y su impresora.`,
      confirmLabel: 'Guardar',
      cuerpo: { action: 'create', nombre, descripcion: nuevaDescripcion.trim() },
      alTerminar: () => { setNuevoNombre(''); setNuevaDescripcion(''); },
    });
  };

  const handleGuardarEdicion = (categoria) => {
    const nombre = edicion.nombre.trim();
    const descripcion = edicion.descripcion.trim();
    if (!nombre) {
      showError('El nombre no puede quedar vacío.');
      return;
    }
    if (nombre === categoria.nombre && descripcion === (categoria.descripcion || '')) {
      setEdicion(null);
      return;
    }
    const cambios = [];
    if (nombre !== categoria.nombre) {
      cambios.push(`cambiar el nombre de «${categoria.nombre}» a «${nombre}»`);
    }
    if (descripcion !== (categoria.descripcion || '')) {
      cambios.push('cambiar la descripción');
    }
    setConfirmacion({
      title: 'Actualizar categoría',
      message: `¿Quieres ${cambios.join(' y ')}?`,
      confirmLabel: 'Actualizar',
      cuerpo: { action: 'update', id: categoria.id, nombre, descripcion },
      alTerminar: () => setEdicion(null),
    });
  };

  const handleToggleActiva = (categoria) => setConfirmacion({
    title: categoria.activa ? 'Desactivar categoría' : 'Activar categoría',
    message: categoria.activa
      ? `¿Desactivar «${categoria.nombre}»? Los meseros dejarán de verla al tomar pedidos`
        + `${categoria.productos ? ` (${textoProductos(categoria.productos)})` : ''}. Los productos no se borran y puedes activarla cuando quieras.`
      : `¿Activar «${categoria.nombre}» otra vez? Los meseros volverán a verla al tomar pedidos.`,
    confirmLabel: categoria.activa ? 'Desactivar' : 'Activar',
    cuerpo: { action: 'update', id: categoria.id, activa: !categoria.activa },
  });

  const handleEliminar = (categoria) => {
    if (categoria.productos > 0) {
      showError(
        `«${categoria.nombre}» tiene ${textoProductos(categoria.productos)}. Muévelos a otra categoría para eliminarla, `
        + 'o desactívala para que los meseros no la vean.',
      );
      return;
    }
    setConfirmacion({
      title: 'Eliminar categoría',
      message: `¿Eliminar la categoría «${categoria.nombre}»? Esta acción no se puede deshacer.`,
      confirmLabel: 'Eliminar',
      cuerpo: { action: 'delete', id: categoria.id },
    });
  };

  const activas = categorias.filter((categoria) => categoria.activa).length;

  return (
    <section style={containerStyle(isMobile)}>
      <button type="button" onClick={onBack} style={backButtonStyle}>← Volver</button>

      <div>
        <h2 style={titleStyle(isMobile)}>Categorías de productos</h2>
        <p style={subtitleStyle}>
          Son las secciones de la carta que ven los meseros (Platos, Bebidas, Pizzas...). Si desactivas una, los meseros
          dejan de verla al tomar pedidos; sus productos siguen guardados. La impresora de cada categoría se asigna en
          Impresoras, y cada producto se asigna a su categoría en Productos.
        </p>
      </div>

      <Toast toast={toast} onClose={hideToast} />

      <form onSubmit={handleCrear} style={panelStyle}>
        <div style={sectionTitleStyle}>Nueva categoría</div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <input
            value={nuevoNombre}
            onChange={(event) => setNuevoNombre(event.target.value)}
            placeholder="Nombre. Ej.: Pizzas"
            maxLength={100}
            style={{ ...inputStyle, flex: '1 1 220px' }}
          />
          <input
            value={nuevaDescripcion}
            onChange={(event) => setNuevaDescripcion(event.target.value)}
            placeholder="Descripción (opcional)"
            maxLength={255}
            style={{ ...inputStyle, flex: '2 1 280px' }}
          />
          <button type="submit" style={primaryButtonStyle} disabled={saving}>Crear categoría</button>
        </div>
      </form>

      <section style={panelStyle}>
        <div style={sectionTitleStyle}>Categorías</div>
        {loading ? <div style={emptyStyle}>Cargando...</div> : null}
        {!loading && categorias.length === 0 ? (
          <div style={emptyStyle}>Aún no hay categorías. Crea la primera arriba.</div>
        ) : null}

        {!loading && categorias.length > 0 ? (
          <div style={tableWrapStyle}>
            <div style={tableStyle}>
              <div style={headStyle}>Categoría</div>
              <div style={headStyle}>Productos</div>
              <div style={headStyle}>Estado</div>
              <div style={headStyle}>Acciones</div>
              {categorias.map((categoria) => {
                const editando = edicion?.id === categoria.id;
                const apagada = !categoria.activa;
                return (
                  <div key={categoria.id} style={{ display: 'contents' }}>
                    <div style={{ ...cellStyle, opacity: apagada && !editando ? 0.6 : 1 }}>
                      {editando ? (
                        <div style={{ display: 'grid', gap: 8 }}>
                          <input
                            value={edicion.nombre}
                            onChange={(event) => setEdicion({ ...edicion, nombre: event.target.value })}
                            maxLength={100}
                            disabled={categoria.protegida}
                            title={categoria.protegida ? 'El sistema usa este nombre: no se puede cambiar.' : undefined}
                            style={inputStyle}
                            autoFocus
                          />
                          <input
                            value={edicion.descripcion}
                            onChange={(event) => setEdicion({ ...edicion, descripcion: event.target.value })}
                            maxLength={255}
                            placeholder="Descripción (opcional)"
                            style={inputStyle}
                          />
                        </div>
                      ) : (
                        <>
                          <strong>
                            {categoria.nombre}
                            {categoria.protegida ? <span style={sistemaBadgeStyle} title="El sistema usa este nombre: no se puede renombrar ni eliminar">Del sistema</span> : null}
                          </strong>
                          {categoria.descripcion ? <span style={mutedStyle}>{categoria.descripcion}</span> : null}
                        </>
                      )}
                    </div>
                    <div style={cellStyle}>
                      {categoria.productos}
                      {categoria.productos !== categoria.productos_disponibles ? (
                        <span style={mutedStyle}>{categoria.productos_disponibles} disponibles</span>
                      ) : null}
                    </div>
                    <div style={cellStyle}>
                      <span style={estadoBadgeStyle(categoria.activa)}>{categoria.activa ? 'Activa' : 'Inactiva'}</span>
                      {apagada ? <span style={mutedStyle}>Los meseros no la ven</span> : null}
                    </div>
                    <div style={cellActionsStyle}>
                      {editando ? (
                        <>
                          <button type="button" style={primaryButtonStyle} disabled={saving} onClick={() => handleGuardarEdicion(categoria)}>Guardar</button>
                          <button type="button" style={secondaryButtonStyle} onClick={() => setEdicion(null)}>Cancelar</button>
                        </>
                      ) : (
                        <>
                          <button
                            type="button"
                            style={secondaryButtonStyle}
                            disabled={saving}
                            onClick={() => setEdicion({ id: categoria.id, nombre: categoria.nombre, descripcion: categoria.descripcion || '' })}
                          >
                            Editar
                          </button>
                          <MenuAcciones
                            disabled={saving}
                            items={[
                              { label: categoria.activa ? 'Desactivar' : 'Activar', onClick: () => handleToggleActiva(categoria) },
                              { label: 'Eliminar', onClick: () => handleEliminar(categoria), danger: true, hidden: categoria.protegida },
                            ]}
                          />
                        </>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ) : null}

        <div style={mutedStyle}>
          {categorias.length} categorías, {activas} activas.
          {onViewProducts ? (
            <>
              {' '}
              <button type="button" onClick={onViewProducts} style={linkButtonStyle}>Ir a Productos</button>
            </>
          ) : null}
        </div>
      </section>

      <ConfirmModal
        open={Boolean(confirmacion)}
        title={confirmacion?.title || ''}
        message={confirmacion?.message || ''}
        confirmLabel={confirmacion?.confirmLabel}
        busy={saving}
        onCancel={() => setConfirmacion(null)}
        onConfirm={confirmar}
      />
    </section>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const titleStyle = (isMobile) => ({ margin: 0, color: 'var(--vg-text-strong)', fontSize: isMobile ? 28 : 34 });
const subtitleStyle = { margin: '8px 0 0', color: 'var(--vg-f-d2c3c3)', lineHeight: 1.6, maxWidth: 760 };
const panelStyle = { display: 'grid', gap: 14, padding: 18, borderRadius: 20, border: '1px solid rgba(var(--vg-ink), 0.1)', background: 'linear-gradient(180deg, var(--vg-bg-card) 0%, var(--vg-s-080808-a980) 100%)' };
const sectionTitleStyle = { color: 'var(--vg-text-strong)', fontSize: 19, fontWeight: 700 };
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(var(--vg-ink), 0.12)', color: 'var(--vg-f-c8bbbb)' };
const mutedStyle = { color: 'var(--vg-f-a89999)', fontSize: 12.5, display: 'block' };
const tableWrapStyle = { overflowX: 'auto' };
const tableStyle = { display: 'grid', gridTemplateColumns: 'minmax(240px,1.6fr) minmax(110px,0.6fr) minmax(150px,0.8fr) minmax(220px,1fr)', minWidth: 760, border: '1px solid rgba(var(--vg-ink), 0.08)', borderRadius: 14, overflow: 'hidden' };
const headStyle = { padding: '12px 14px', background: 'rgba(var(--vg-ink), 0.06)', color: 'var(--vg-f-ffb0b0)', fontSize: 12, letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 800 };
const cellStyle = { padding: '12px 14px', borderTop: '1px solid rgba(var(--vg-ink), 0.08)', color: 'var(--vg-f-f2e6e6)', display: 'grid', alignContent: 'center', gap: 3 };
const cellActionsStyle = { ...cellStyle, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' };
const inputStyle = { borderRadius: 12, border: '1px solid rgba(var(--vg-ink), 0.14)', background: 'var(--vg-s-161010)', padding: '10px 12px', color: 'var(--vg-text-strong)', width: '100%', boxSizing: 'border-box' };
const primaryButtonStyle = { border: 'none', borderRadius: 999, padding: '10px 16px', background: 'linear-gradient(90deg, #bf1f1f 0%, var(--vg-accent-primary) 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const secondaryButtonStyle = { border: '1px solid rgba(var(--vg-ink), 0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(var(--vg-ink), 0.04)', color: 'var(--vg-text-strong)', fontWeight: 700, cursor: 'pointer', width: 'fit-content' };
const linkButtonStyle = { border: 'none', background: 'transparent', color: 'var(--vg-f-ff8f8f)', fontWeight: 700, cursor: 'pointer', padding: 0, textDecoration: 'underline' };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };
const sistemaBadgeStyle = { marginLeft: 8, fontSize: 10.5, fontWeight: 800, padding: '2px 8px', borderRadius: 999, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--vg-f-ffd8a3)', background: 'rgba(255,207,133,0.12)' };
const estadoBadgeStyle = (activa) => ({
  width: 'fit-content',
  fontSize: 11,
  fontWeight: 800,
  padding: '3px 10px',
  borderRadius: 999,
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
  color: activa ? '#bdf0cf' : '#c8bbbb',
  background: activa ? 'rgba(70,200,120,0.16)' : 'rgba(255,255,255,0.08)',
});

export default AnalystProductCategoriesPage;
