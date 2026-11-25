import { useState } from 'react';

/**
 * Pide el código de una subreceta bloqueada y, si es correcto, muestra su receta. No guarda nada: al cerrar
 * se descarta y la próxima vez se vuelve a pedir el código.
 */
function SubrecetaBloqueadaModal({ subreceta, onClose }) {
  const [codigo, setCodigo] = useState('');
  const [receta, setReceta] = useState(null);
  const [mensaje, setMensaje] = useState('');
  const [enviando, setEnviando] = useState(false);

  const abrir = async (event) => {
    event.preventDefault();
    if (!codigo) return;
    setEnviando(true);
    setMensaje('');
    try {
      const response = await fetch('/api/admin/subrecetas/desbloquear/', {
        method: 'POST',
        credentials: 'include',
        cache: 'no-store',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: subreceta.id, codigo }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo abrir la subreceta.');
      }
      setReceta(data.subreceta);
    } catch (error) {
      setMensaje(error.message || 'No se pudo abrir la subreceta.');
    } finally {
      setCodigo('');
      setEnviando(false);
    }
  };

  return (
    <div style={fondoStyle} onClick={onClose}>
      <div role="dialog" aria-label={`Subreceta bloqueada: ${subreceta.nombre}`} style={cajaStyle} onClick={(e) => e.stopPropagation()}>
        <div style={tituloStyle}>🔒 {subreceta.nombre}</div>

        {!receta ? (
          <form onSubmit={abrir} style={{ display: 'grid', gap: 12 }}>
            <label style={{ display: 'grid', gap: 6 }}>
              <span style={etiquetaStyle}>Código de acceso</span>
              <input
                type="password"
                value={codigo}
                onChange={(e) => setCodigo(e.target.value)}
                autoFocus
                autoComplete="off"
                style={inputStyle}
              />
            </label>
            {mensaje ? <div role="alert" style={errorStyle}>{mensaje}</div> : null}
            <div style={botonesStyle}>
              <button type="button" onClick={onClose} style={secundarioStyle}>Cancelar</button>
              <button type="submit" style={primarioStyle} disabled={!codigo || enviando}>
                {enviando ? 'Verificando...' : 'Ver receta'}
              </button>
            </div>
          </form>
        ) : (
          <div style={{ display: 'grid', gap: 10 }}>
            <div style={etiquetaStyle}>Rinde {receta.rendimiento_cantidad} {receta.rendimiento_unidad}</div>
            {receta.componentes.map((componente) => (
              <div key={`${componente.tipo}-${componente.nombre}`} style={filaStyle}>
                <span>{componente.bloqueada ? '🔒 ' : ''}{componente.nombre}</span>
                <strong>{componente.cantidad} {componente.unidad}</strong>
              </div>
            ))}
            <div style={filaStyle}>
              <span>Costo de la tanda</span>
              <strong>${receta.costo_total}</strong>
            </div>
            <div style={filaStyle}>
              <span>Costo por {receta.rendimiento_unidad}</span>
              <strong>${Number(receta.costo_unitario).toFixed(4)}</strong>
            </div>
            <div style={botonesStyle}>
              <button type="button" onClick={onClose} style={primarioStyle}>Cerrar</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

const fondoStyle = { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.65)', display: 'grid', placeItems: 'center', zIndex: 60, padding: 16 };
const cajaStyle = { width: 'min(460px, 100%)', maxHeight: '85vh', overflowY: 'auto', display: 'grid', gap: 14, padding: 20, borderRadius: 18, border: '1px solid rgba(var(--vg-ink), 0.14)', background: 'var(--vg-bg-card)' };
const tituloStyle = { color: 'var(--vg-text-strong)', fontSize: 20, fontWeight: 800 };
const etiquetaStyle = { color: 'var(--vg-f-c8bbbb)', fontSize: 13, fontWeight: 700 };
const inputStyle = { borderRadius: 12, border: '1px solid rgba(var(--vg-ink), 0.16)', background: 'var(--vg-s-161010)', padding: '12px 14px', color: 'var(--vg-text-strong)', fontSize: 16 };
const errorStyle = { color: 'var(--vg-f-ff9d9d)', fontSize: 13, fontWeight: 700 };
const filaStyle = { display: 'flex', justifyContent: 'space-between', gap: 12, color: 'var(--vg-f-f2e6e6)', borderBottom: '1px solid rgba(var(--vg-ink), 0.08)', paddingBottom: 6 };
const botonesStyle = { display: 'flex', justifyContent: 'flex-end', gap: 10, flexWrap: 'wrap' };
const primarioStyle = { border: 'none', borderRadius: 999, padding: '10px 16px', background: 'linear-gradient(90deg, #bf1f1f 0%, var(--vg-accent-primary) 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const secundarioStyle = { border: '1px solid rgba(var(--vg-ink), 0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(var(--vg-ink), 0.04)', color: 'var(--vg-text-strong)', fontWeight: 700, cursor: 'pointer' };

export default SubrecetaBloqueadaModal;
