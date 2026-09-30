import { useEffect, useState } from 'react';
import Toast from './Toast';
import useToast from '../hooks/useToast';

const initialForm = { metodo_pago_id: '', monto: '', descripcion: '' };

function simboloMoneda(moneda) {
  if (moneda === 'USD') return '$';
  if (moneda === 'VES') return 'Bs';
  return moneda || '';
}

function IngresoNoFacturadoModal({ open, onClose, onSuccess }) {
  const [metodos, setMetodos] = useState([]);
  const [form, setForm] = useState(initialForm);
  const [submitting, setSubmitting] = useState(false);
  const { toast, showError, hideToast } = useToast();

  useEffect(() => {
    if (!open) return;
    setForm(initialForm);
    const loadMetodos = async () => {
      try {
        const response = await fetch('/api/metodos-pago/', { credentials: 'include', cache: 'no-store' });
        const data = await response.json();
        if (response.ok && data.ok) {
          setMetodos(Array.isArray(data.metodos_pago) ? data.metodos_pago : []);
        }
      } catch (error) {
        showError('No se pudieron cargar las cuentas.');
      }
    };
    loadMetodos();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const cuentaSeleccionada = metodos.find((metodo) => String(metodo.id) === String(form.metodo_pago_id)) || null;

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!form.metodo_pago_id) {
      showError('Selecciona la cuenta donde entró el dinero.');
      return;
    }
    const montoNum = Number(form.monto);
    if (!Number.isFinite(montoNum) || montoNum <= 0) {
      showError('El monto debe ser mayor a cero.');
      return;
    }
    if (!form.descripcion.trim()) {
      showError('La descripción es obligatoria para un ingreso no facturado.');
      return;
    }

    setSubmitting(true);
    try {
      const response = await fetch('/api/contabilidad/ingresos-extra/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tipo: 'ingreso_no_facturado',
          metodo_pago_id: form.metodo_pago_id,
          monto: form.monto,
          descripcion: form.descripcion,
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo registrar el ingreso.');
      }
      onSuccess(data);
    } catch (error) {
      showError(error.message || 'No se pudo registrar el ingreso.');
    } finally {
      setSubmitting(false);
    }
  };

  if (!open) {
    return null;
  }

  return (
    <div style={backdropStyle} onClick={submitting ? undefined : onClose}>
      <div style={cardStyle} onClick={(event) => event.stopPropagation()}>
        <div style={titleStyle}>Registrar ingreso no facturado</div>
        <p style={hintStyle}>
          Dinero que entró a una cuenta sin pasar por un cobro de venta — un depósito de un socio, un reembolso de un
          proveedor, etc.
        </p>

        <Toast toast={toast} onClose={hideToast} />

        <form onSubmit={handleSubmit} style={formStyle}>
          <label style={fieldStyle}>
            <span style={labelStyle}>Cuenta</span>
            <select
              value={form.metodo_pago_id}
              onChange={(event) => setForm((current) => ({ ...current, metodo_pago_id: event.target.value }))}
              style={inputStyle}
              required
            >
              <option value="">Selecciona...</option>
              {metodos.map((metodo) => (
                <option key={metodo.id} value={metodo.id}>{metodo.nombre} ({metodo.moneda})</option>
              ))}
            </select>
          </label>

          <label style={fieldStyle}>
            <span style={labelStyle}>Monto {cuentaSeleccionada ? `(${simboloMoneda(cuentaSeleccionada.moneda)})` : ''}</span>
            <input
              type="number"
              step="0.01"
              min="0.01"
              value={form.monto}
              onChange={(event) => setForm((current) => ({ ...current, monto: event.target.value }))}
              style={inputStyle}
              required
            />
          </label>

          <label style={fieldStyle}>
            <span style={labelStyle}>Descripción (obligatoria)</span>
            <input
              value={form.descripcion}
              onChange={(event) => setForm((current) => ({ ...current, descripcion: event.target.value }))}
              style={inputStyle}
              placeholder="Ej. Depósito de un socio, reembolso de proveedor..."
              required
            />
          </label>

          <div style={footerStyle}>
            <button type="button" onClick={onClose} style={cancelButtonStyle} disabled={submitting}>
              Cancelar
            </button>
            <button type="submit" style={confirmButtonStyle} disabled={submitting}>
              {submitting ? 'Guardando...' : 'Registrar ingreso'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

const backdropStyle = {
  position: 'fixed',
  inset: 0,
  background: 'rgba(0, 0, 0, 0.6)',
  display: 'grid',
  placeItems: 'center',
  zIndex: 1000,
  padding: 16,
};

const cardStyle = {
  width: '100%',
  maxWidth: 460,
  maxHeight: '90vh',
  overflowY: 'auto',
  borderRadius: 20,
  border: '1px solid rgba(45, 212, 191, 0.3)',
  background: 'linear-gradient(180deg, rgba(10, 22, 20, 0.98) 0%, rgba(8, 10, 10, 0.99) 100%)',
  padding: '22px 22px 18px',
  boxShadow: '0 20px 50px rgba(0, 0, 0, 0.45)',
};

const titleStyle = { color: '#fff', fontSize: 19, fontWeight: 800, marginBottom: 6 };
const hintStyle = { color: '#a9d9d0', fontSize: 12.5, lineHeight: 1.5, margin: '0 0 14px' };

const formStyle = { display: 'grid', gap: 14 };
const fieldStyle = { display: 'grid', gap: 6 };
const labelStyle = { color: '#7fe6d3', fontSize: 12.5, fontWeight: 700 };
const inputStyle = {
  width: '100%',
  boxSizing: 'border-box',
  padding: '10px 12px',
  borderRadius: 12,
  border: '1px solid rgba(255, 255, 255, 0.16)',
  background: 'rgba(255, 255, 255, 0.05)',
  color: '#fff',
  fontSize: 14,
};

const footerStyle = { display: 'flex', justifyContent: 'space-between', gap: 10, marginTop: 6, flexWrap: 'wrap' };
const cancelButtonStyle = {
  border: '1px solid rgba(255, 255, 255, 0.16)',
  borderRadius: 999,
  padding: '10px 16px',
  background: 'rgba(255, 255, 255, 0.05)',
  color: '#fff',
  fontWeight: 700,
  cursor: 'pointer',
};
const confirmButtonStyle = {
  border: 'none',
  borderRadius: 999,
  padding: '10px 18px',
  background: 'linear-gradient(90deg, #0d9488 0%, #14b8a6 100%)',
  color: '#04140f',
  fontWeight: 700,
  cursor: 'pointer',
  boxShadow: '0 8px 20px rgba(13, 148, 136, 0.35)',
};

export default IngresoNoFacturadoModal;
