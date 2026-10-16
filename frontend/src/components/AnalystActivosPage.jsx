import { useCallback, useEffect, useState } from 'react';
import BotonDescargarPdf from './BotonDescargarPdf';
import ConfirmModal from './ConfirmModal';
import MenuAcciones from './MenuAcciones';
import Toast from './Toast';
import useToast from '../hooks/useToast';
import descargarPdf from '../utils/descargarPdf';

const TIPOS = [
  { value: 'equipo', label: 'Equipo / mobiliario' },
  { value: 'dotacion', label: 'Dotación (se entrega a empleados)' },
];
const ESTADOS = [
  { value: 'bueno', label: 'Bueno' },
  { value: 'regular', label: 'Regular' },
  { value: 'danado', label: 'Dañado' },
  { value: 'baja', label: 'Dado de baja' },
];
const MOVIMIENTOS = [
  { value: 'entrega', label: 'Entrega a empleado' },
  { value: 'entrada', label: 'Entrada (compra)' },
  { value: 'baja', label: 'Baja (rota, perdida...)' },
  { value: 'ajuste', label: 'Ajuste de conteo' },
];

const formVacio = {
  id: null, nombre: '', tipo: 'equipo', categoria_id: '', cantidad: '', cantidad_minima: '', estado: 'bueno',
  ubicacion: '', valor_unitario: '', fecha_adquisicion: '', proveedor: '', serial: '', notas: '',
};
const movimientoVacio = { activo: null, tipo: 'entrega', cantidad: '', motivo: '', receptor: '' };

async function pedir(url, opciones) {
  const response = await fetch(url, { credentials: 'include', cache: 'no-store', ...opciones });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.ok) {
    throw new Error(data.message || 'No se pudo completar la operación.');
  }
  return data;
}

const enviar = (cuerpo) => pedir('/api/admin/activos/', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(cuerpo),
});

// Utensilios y equipos del restaurante (neveras, platos, impresoras, franelas...). Son aparte de los
// ingredientes: no entran a recetas ni al estado de resultados. Cada guardar, actualizar, eliminar o
// movimiento de cantidad pide confirmación antes de ejecutarse.
function AnalystActivosPage({ isMobile, onBack, onCategorias, onMovimientos }) {
  const { toast, showSuccess, showError, hideToast } = useToast();
  const [activos, setActivos] = useState([]);
  const [resumen, setResumen] = useState(null);
  const [categorias, setCategorias] = useState([]);
  const [ubicaciones, setUbicaciones] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [filtros, setFiltros] = useState({ tipo: '', categoria_id: '', estado: '', ubicacion: '', q: '' });
  const [form, setForm] = useState(null);
  const [mov, setMov] = useState(null);
  const [historial, setHistorial] = useState(null);
  const [confirmacion, setConfirmacion] = useState(null); // { title, message, confirmLabel, ejecutar }
  const [ultimaEntrega, setUltimaEntrega] = useState(null);

  const cargar = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams(Object.entries(filtros).filter(([, valor]) => valor));
      const data = await pedir(`/api/admin/activos/?${params.toString()}`);
      setActivos(data.activos || []);
      setResumen(data.resumen || null);
      setCategorias(data.categorias || []);
      setUbicaciones(data.ubicaciones || []);
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

  const cambiarFiltro = (campo, valor) => setFiltros((actual) => ({ ...actual, [campo]: valor }));

  // Ejecuta la acción ya confirmada: muestra el resultado, cierra el diálogo y recarga.
  const confirmar = async () => {
    if (!confirmacion) {
      return;
    }
    setSaving(true);
    try {
      const data = await confirmacion.ejecutar();
      showSuccess(data.message || 'Listo.');
      if (confirmacion.alTerminar) {
        confirmacion.alTerminar(data);
      }
      await cargar();
    } catch (error) {
      showError(error.message);
    } finally {
      setSaving(false);
      setConfirmacion(null);
    }
  };

  const pedirGuardar = (event) => {
    event.preventDefault();
    if (!form.nombre.trim()) {
      showError('Escribe el nombre del artículo.');
      return;
    }
    const esNuevo = !form.id;
    setConfirmacion({
      title: esNuevo ? 'Guardar artículo' : 'Actualizar artículo',
      message: esNuevo
        ? `¿Guardar «${form.nombre.trim()}» en el inventario de utensilios y equipos?`
        : `¿Actualizar los datos de «${form.nombre.trim()}»? La cantidad no cambia desde aquí: usa «Mover cantidad».`,
      confirmLabel: esNuevo ? 'Guardar' : 'Actualizar',
      ejecutar: () => enviar({ action: esNuevo ? 'create' : 'update', ...form, categoria_id: form.categoria_id || '' }),
      alTerminar: () => setForm(null),
    });
  };

  const pedirEliminar = (activo) => setConfirmacion({
    title: 'Eliminar artículo',
    message: `¿Eliminar «${activo.nombre}»? También se borra su historial de movimientos y esta acción no se puede deshacer.`,
    confirmLabel: 'Eliminar',
    ejecutar: () => enviar({ action: 'delete', id: activo.id }),
  });

  const pedirMovimiento = (event) => {
    event.preventDefault();
    const { activo, tipo, cantidad, motivo, receptor } = mov;
    if (!(Number(cantidad) >= (tipo === 'ajuste' ? 0 : 1)) || cantidad === '') {
      showError(tipo === 'ajuste' ? 'Indica la cantidad contada.' : 'Indica una cantidad mayor a cero.');
      return;
    }
    if (tipo === 'entrega' && !receptor.trim()) {
      showError('Escribe a quién se le entrega.');
      return;
    }
    if ((tipo === 'baja' || tipo === 'ajuste') && !motivo.trim()) {
      showError('Indica el motivo.');
      return;
    }
    const descripcion = {
      entrega: `entregar ${cantidad} de «${activo.nombre}» a ${receptor.trim().replace(/\s+/g, ' ')}`,
      entrada: `sumar ${cantidad} a «${activo.nombre}»`,
      baja: `dar de baja ${cantidad} de «${activo.nombre}»`,
      ajuste: `dejar «${activo.nombre}» en ${cantidad} (hoy hay ${activo.cantidad})`,
    }[tipo];
    setConfirmacion({
      title: 'Confirmar movimiento',
      message: `¿Confirmas ${descripcion}?`,
      confirmLabel: 'Confirmar',
      ejecutar: () => enviar({ action: 'movimiento', id: activo.id, tipo, cantidad, motivo: motivo.trim(), receptor: receptor.trim() }),
      alTerminar: (data) => {
        setMov(null);
        setUltimaEntrega(tipo === 'entrega' ? data.movimiento : null);
      },
    });
  };

  const abrirHistorial = async (activo) => {
    try {
      const data = await pedir(`/api/admin/activos/?movimientos_de=${activo.id}`);
      setHistorial(data);
    } catch (error) {
      showError(error.message);
    }
  };

  const editar = (activo) => {
    setMov(null);
    setForm({
      ...formVacio,
      id: activo.id,
      nombre: activo.nombre,
      tipo: activo.tipo,
      categoria_id: activo.categoria ?? '',
      cantidad_minima: activo.cantidad_minima || '',
      estado: activo.estado,
      ubicacion: activo.ubicacion,
      valor_unitario: activo.valor_unitario ?? '',
      fecha_adquisicion: activo.fecha_adquisicion || '',
      proveedor: activo.proveedor,
      serial: activo.serial,
      notas: activo.notas,
    });
  };

  const campo = (etiqueta, nombre, props = {}) => (
    <label style={fieldStyle}>
      <span>{etiqueta}</span>
      <input
        value={form[nombre]}
        onChange={(event) => setForm((actual) => ({ ...actual, [nombre]: event.target.value }))}
        style={inputStyle}
        {...props}
      />
    </label>
  );

  return (
    <section style={containerStyle(isMobile)}>
      <button type="button" onClick={onBack} style={backButtonStyle}>← Volver</button>

      <div style={headerRowStyle(isMobile)}>
        <div>
          <h2 style={titleStyle(isMobile)}>Utensilios y equipos</h2>
          <p style={subtitleStyle}>
            Neveras, platos, impresoras, franelas para los empleados... Van aparte de los ingredientes: no entran a
            las recetas, no mueven el stock de cocina ni afectan el estado de resultados.
          </p>
        </div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
          <button type="button" style={primaryButtonStyle} onClick={() => { setMov(null); setForm({ ...formVacio }); }}>
            + Nuevo artículo
          </button>
          <MenuAcciones
            label="Más acciones"
            items={[
              {
                label: 'Descargar PDF',
                onClick: () => descargarPdf('/api/admin/reportes/inventario-general-pdf/', {
                  tipo: 'utensilios',
                  categoria: filtros.categoria_id ? (filtros.categoria_id === 'sin' ? 'sin' : `a:${filtros.categoria_id}`) : '',
                  q: filtros.q,
                }).catch((error) => showError(error.message || 'No se pudo generar el PDF.')),
              },
              { label: 'Categorías de utensilios', onClick: onCategorias, hidden: !onCategorias },
              { label: 'Ver todos los movimientos', onClick: onMovimientos, hidden: !onMovimientos },
            ]}
          />
        </div>
      </div>

      <Toast toast={toast} onClose={hideToast} />

      {ultimaEntrega ? (
        <div style={avisoStyle}>
          <span>
            Entrega registrada a <strong>{ultimaEntrega.receptor}</strong> — comprobante <strong>{ultimaEntrega.comprobante}</strong>.
          </span>
          <BotonDescargarPdf
            url={`/api/admin/activos/entregas/${ultimaEntrega.id}/comprobante-pdf/`}
            onError={showError}
          >
            Imprimir comprobante
          </BotonDescargarPdf>
          <button type="button" style={secondaryButtonStyle} onClick={() => setUltimaEntrega(null)}>Cerrar</button>
        </div>
      ) : null}

      {form ? (
        <form onSubmit={pedirGuardar} style={panelStyle}>
          <div style={sectionTitleStyle}>{form.id ? 'Modificar artículo' : 'Nuevo artículo'}</div>
          <div style={formGridStyle(isMobile)}>
            {campo('Nombre *', 'nombre', { maxLength: 150, placeholder: 'Ej.: Nevera vertical, Franela M' })}
            <label style={fieldStyle}>
              <span>Tipo</span>
              <select value={form.tipo} onChange={(e) => setForm((a) => ({ ...a, tipo: e.target.value }))} style={inputStyle} className="admin-dark-select">
                {TIPOS.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
            </label>
            <label style={fieldStyle}>
              <span>Categoría</span>
              <select value={form.categoria_id} onChange={(e) => setForm((a) => ({ ...a, categoria_id: e.target.value }))} style={inputStyle} className="admin-dark-select">
                <option value="">Sin categoría</option>
                {categorias
                  .filter((c) => c.activo || String(c.id) === String(form.categoria_id))
                  .map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}
              </select>
            </label>
            {!form.id ? campo('Cantidad inicial', 'cantidad', { type: 'number', min: 0, step: 1, placeholder: '0' }) : null}
            {campo('Aviso si baja de', 'cantidad_minima', { type: 'number', min: 0, step: 1, placeholder: '0 = sin aviso' })}
            <label style={fieldStyle}>
              <span>Estado</span>
              <select value={form.estado} onChange={(e) => setForm((a) => ({ ...a, estado: e.target.value }))} style={inputStyle} className="admin-dark-select">
                {ESTADOS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
              </select>
            </label>
            {campo('Ubicación', 'ubicacion', { list: 'ubicaciones-activos', maxLength: 80, placeholder: 'Cocina, barra, salón, caja, almacén...' })}
            <datalist id="ubicaciones-activos">
              {['Cocina', 'Barra', 'Salón', 'Caja', 'Almacén', ...ubicaciones].filter((u, i, lista) => lista.indexOf(u) === i).map((u) => <option key={u} value={u} />)}
            </datalist>
            {campo('Valor unitario ($, informativo)', 'valor_unitario', { type: 'number', min: 0, step: '0.01' })}
            {campo('Fecha de adquisición', 'fecha_adquisicion', { type: 'date' })}
            {campo('Proveedor', 'proveedor', { maxLength: 150 })}
            {campo('Serial / código', 'serial', { maxLength: 100 })}
          </div>
          <label style={fieldStyle}>
            <span>Notas</span>
            <textarea
              value={form.notas}
              onChange={(e) => setForm((a) => ({ ...a, notas: e.target.value }))}
              rows={2}
              style={{ ...inputStyle, resize: 'vertical' }}
            />
          </label>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <button type="submit" style={primaryButtonStyle} disabled={saving}>{form.id ? 'Actualizar' : 'Guardar'}</button>
            <button type="button" style={secondaryButtonStyle} onClick={() => setForm(null)}>Cancelar</button>
          </div>
        </form>
      ) : null}

      {mov ? (
        <form onSubmit={pedirMovimiento} style={panelStyle}>
          <div style={sectionTitleStyle}>Mover cantidad de «{mov.activo.nombre}» (hay {mov.activo.cantidad})</div>
          <div style={formGridStyle(isMobile)}>
            <label style={fieldStyle}>
              <span>Movimiento</span>
              <select value={mov.tipo} onChange={(e) => setMov((a) => ({ ...a, tipo: e.target.value }))} style={inputStyle} className="admin-dark-select">
                {MOVIMIENTOS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
              </select>
            </label>
            <label style={fieldStyle}>
              <span>{mov.tipo === 'ajuste' ? 'Cantidad contada' : 'Cantidad'}</span>
              <input type="number" min={mov.tipo === 'ajuste' ? 0 : 1} step={1} value={mov.cantidad} onChange={(e) => setMov((a) => ({ ...a, cantidad: e.target.value }))} style={inputStyle} />
            </label>
            {mov.tipo === 'entrega' ? (
              <label style={fieldStyle}>
                <span>Quién recibe *</span>
                <input value={mov.receptor} maxLength={150} onChange={(e) => setMov((a) => ({ ...a, receptor: e.target.value }))} style={inputStyle} placeholder="Nombre del empleado" />
              </label>
            ) : null}
            <label style={fieldStyle}>
              <span>Motivo / nota{mov.tipo === 'baja' || mov.tipo === 'ajuste' ? ' *' : ''}</span>
              <input value={mov.motivo} maxLength={255} onChange={(e) => setMov((a) => ({ ...a, motivo: e.target.value }))} style={inputStyle} />
            </label>
          </div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <button type="submit" style={primaryButtonStyle} disabled={saving}>Registrar movimiento</button>
            <button type="button" style={secondaryButtonStyle} onClick={() => setMov(null)}>Cancelar</button>
          </div>
        </form>
      ) : null}

      <section style={panelStyle}>
        <div style={filtrosStyle(isMobile)}>
          <select value={filtros.tipo} onChange={(e) => cambiarFiltro('tipo', e.target.value)} style={inputStyle} className="admin-dark-select">
            <option value="">Todos los tipos</option>
            {TIPOS.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
          <select value={filtros.categoria_id} onChange={(e) => cambiarFiltro('categoria_id', e.target.value)} style={inputStyle} className="admin-dark-select">
            <option value="">Todas las categorías</option>
            <option value="sin">Sin categoría</option>
            {categorias.map((c) => <option key={c.id} value={c.id}>{c.nombre}{c.activo ? '' : ' (inactiva)'}</option>)}
          </select>
          <select value={filtros.estado} onChange={(e) => cambiarFiltro('estado', e.target.value)} style={inputStyle} className="admin-dark-select">
            <option value="">Todos los estados</option>
            {ESTADOS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
          <select value={filtros.ubicacion} onChange={(e) => cambiarFiltro('ubicacion', e.target.value)} style={inputStyle} className="admin-dark-select">
            <option value="">Todas las ubicaciones</option>
            {ubicaciones.map((u) => <option key={u} value={u}>{u}</option>)}
          </select>
          <input value={filtros.q} onChange={(e) => cambiarFiltro('q', e.target.value)} placeholder="Buscar por nombre, serial o proveedor" style={inputStyle} />
        </div>

        {resumen ? (
          <div style={mutedStyle}>
            {resumen.articulos} artículo(s) · {resumen.unidades} unidades · valor de compra ${resumen.valor_total}
            {resumen.bajo_minimo > 0 ? ` · ⚠ ${resumen.bajo_minimo} bajo el mínimo` : ''}
          </div>
        ) : null}

        {loading ? <div style={emptyStyle}>Cargando...</div> : null}
        {!loading && activos.length === 0 ? <div style={emptyStyle}>No hay artículos con ese filtro.</div> : null}

        {!loading && activos.length > 0 ? (
          <div style={tableWrapStyle}>
            <div style={tableStyle}>
              <div style={headStyle}>Artículo</div>
              <div style={headStyle}>Categoría</div>
              <div style={headStyle}>Ubicación</div>
              <div style={headStyle}>Estado</div>
              <div style={{ ...headStyle, textAlign: 'right' }}>Cantidad</div>
              <div style={{ ...headStyle, textAlign: 'right' }}>Valor total</div>
              <div style={headStyle}>Acciones</div>
              {activos.map((activo) => (
                <div key={activo.id} style={{ display: 'contents' }}>
                  <div style={cellStyle}>
                    <strong>{activo.nombre}</strong>
                    <span style={mutedStyle}>{activo.tipo_label}{activo.serial ? ` · ${activo.serial}` : ''}</span>
                  </div>
                  <div style={cellStyle}>{activo.categoria_nombre || '—'}</div>
                  <div style={cellStyle}>{activo.ubicacion || '—'}</div>
                  <div style={cellStyle}>{activo.estado_label}</div>
                  <div style={{ ...cellStyle, textAlign: 'right', fontWeight: 700, color: activo.bajo_minimo ? 'var(--vg-f-ffcf7d)' : undefined }}>
                    {activo.cantidad}{activo.bajo_minimo ? ' ⚠' : ''}
                  </div>
                  <div style={{ ...cellStyle, textAlign: 'right' }}>{activo.valor_unitario !== null ? `$${activo.valor_total}` : '—'}</div>
                  <div style={cellActionsStyle}>
                    <button type="button" style={miniButtonStyle} onClick={() => { setForm(null); setMov({ ...movimientoVacio, activo, tipo: activo.tipo === 'dotacion' ? 'entrega' : 'baja' }); }}>Mover cantidad</button>
                    <MenuAcciones
                      items={[
                        { label: 'Modificar', onClick: () => editar(activo) },
                        { label: 'Historial de movimientos', onClick: () => abrirHistorial(activo) },
                        { label: 'Eliminar', onClick: () => pedirEliminar(activo), danger: true },
                      ]}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </section>

      {historial ? (
        <div style={backdropStyle} onClick={() => setHistorial(null)}>
          <div style={modalStyle} onClick={(event) => event.stopPropagation()}>
            <div style={sectionTitleStyle}>Historial de «{historial.activo.nombre}»</div>
            {historial.movimientos.length === 0 ? <div style={emptyStyle}>Sin movimientos.</div> : (
              <div style={{ display: 'grid', gap: 8, maxHeight: '60vh', overflowY: 'auto' }}>
                {historial.movimientos.map((m) => (
                  <div key={m.id} style={movimientoRowStyle}>
                    <div style={{ display: 'grid', gap: 2 }}>
                      <strong>
                        {m.tipo_label} {m.delta > 0 ? `+${m.delta}` : m.delta} → {m.cantidad_resultante}
                      </strong>
                      <span style={mutedStyle}>
                        {new Date(m.fecha).toLocaleString('es-VE', { dateStyle: 'short', timeStyle: 'short' })}
                        {m.registrado_por ? ` · ${m.registrado_por}` : ''}
                        {m.receptor ? ` · Recibió: ${m.receptor}` : ''}
                        {m.motivo ? ` · ${m.motivo}` : ''}
                      </span>
                    </div>
                    {m.comprobante ? (
                      <BotonDescargarPdf url={`/api/admin/activos/entregas/${m.id}/comprobante-pdf/`} onError={showError}>
                        {m.comprobante}
                      </BotonDescargarPdf>
                    ) : null}
                  </div>
                ))}
              </div>
            )}
            <div><button type="button" style={secondaryButtonStyle} onClick={() => setHistorial(null)}>Cerrar</button></div>
          </div>
        </div>
      ) : null}

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
const headerRowStyle = (isMobile) => ({ display: 'flex', justifyContent: 'space-between', alignItems: isMobile ? 'flex-start' : 'center', flexDirection: isMobile ? 'column' : 'row', gap: 12 });
const titleStyle = (isMobile) => ({ margin: 0, color: 'var(--vg-text-strong)', fontSize: isMobile ? 28 : 34 });
const subtitleStyle = { margin: '8px 0 0', color: 'var(--vg-f-d2c3c3)', lineHeight: 1.6, maxWidth: 720 };
const panelStyle = { display: 'grid', gap: 14, padding: 18, borderRadius: 20, border: '1px solid rgba(var(--vg-ink), 0.1)', background: 'linear-gradient(180deg, var(--vg-bg-card) 0%, var(--vg-s-080808-a980) 100%)' };
const avisoStyle = { display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center', padding: '12px 14px', borderRadius: 14, border: '1px solid var(--vg-f-34d399-a400)', background: 'rgba(52, 211, 153, 0.1)', color: 'var(--vg-text-strong)' };
const sectionTitleStyle = { color: 'var(--vg-text-strong)', fontSize: 19, fontWeight: 700 };
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(var(--vg-ink), 0.12)', color: 'var(--vg-f-c8bbbb)' };
const mutedStyle = { color: 'var(--vg-f-a89999)', fontSize: 12.5, display: 'block' };
const formGridStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, minmax(0, 1fr))', gap: 12 });
const filtrosStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(5, minmax(0, 1fr))', gap: 10 });
const fieldStyle = { display: 'grid', gap: 6, color: 'var(--vg-f-f2e6e6)', fontSize: 13, fontWeight: 700 };
const inputStyle = { borderRadius: 12, border: '1px solid rgba(var(--vg-ink), 0.14)', background: 'var(--vg-s-161010)', padding: '10px 12px', color: 'var(--vg-text-strong)', width: '100%', boxSizing: 'border-box' };
const tableWrapStyle = { overflowX: 'auto' };
const tableStyle = { display: 'grid', gridTemplateColumns: 'minmax(190px,1.3fr) minmax(130px,0.8fr) minmax(110px,0.7fr) minmax(100px,0.6fr) minmax(90px,0.5fr) minmax(110px,0.6fr) minmax(190px,0.9fr)', minWidth: 960, border: '1px solid rgba(var(--vg-ink), 0.08)', borderRadius: 14, overflow: 'hidden' };
const headStyle = { padding: '12px 14px', background: 'rgba(var(--vg-ink), 0.06)', color: 'var(--vg-f-ffb0b0)', fontSize: 12, letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 800 };
const cellStyle = { padding: '12px 14px', borderTop: '1px solid rgba(var(--vg-ink), 0.08)', color: 'var(--vg-f-f2e6e6)', display: 'grid', alignContent: 'center', gap: 2 };
const cellActionsStyle = { ...cellStyle, display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' };
const primaryButtonStyle = { border: 'none', borderRadius: 999, padding: '10px 16px', background: 'linear-gradient(90deg, #bf1f1f 0%, var(--vg-accent-primary) 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const secondaryButtonStyle = { border: '1px solid rgba(var(--vg-ink), 0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(var(--vg-ink), 0.04)', color: 'var(--vg-text-strong)', fontWeight: 700, cursor: 'pointer', width: 'fit-content' };
const miniButtonStyle = { border: '1px solid rgba(var(--vg-ink), 0.18)', borderRadius: 999, padding: '6px 12px', background: 'rgba(var(--vg-ink), 0.05)', color: 'var(--vg-text-strong)', fontWeight: 700, cursor: 'pointer', fontSize: 12.5 };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };
const backdropStyle = { position: 'fixed', inset: 0, background: 'rgba(0, 0, 0, 0.65)', display: 'grid', placeItems: 'center', zIndex: 900, padding: 16 };
const modalStyle = { width: 'min(640px, 100%)', display: 'grid', gap: 14, padding: 22, borderRadius: 20, border: '1px solid rgba(var(--vg-ink), 0.14)', background: 'var(--vg-s-140b0b)' };
const movimientoRowStyle = { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, padding: '10px 12px', borderRadius: 12, border: '1px solid rgba(var(--vg-ink), 0.08)', color: 'var(--vg-f-f2e6e6)' };

export default AnalystActivosPage;
