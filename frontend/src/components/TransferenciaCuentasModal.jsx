import { useEffect, useMemo, useState } from 'react';
import Toast from './Toast';
import useToast from '../hooks/useToast';

function formatMonto(value) {
  const number = Number(value || 0);
  return number.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

const initialForm = {
  cuenta_origen_id: '',
  cuenta_destino_id: '',
  monto_origen: '',
  monto_destino: '',
  tasa_cambio: '',
  referencia: '',
  concepto: '',
};

function TransferenciaCuentasModal({ open, fechaInicial, onClose, onSuccess }) {
  const [fecha, setFecha] = useState(fechaInicial);
  const [metodos, setMetodos] = useState([]);
  const [saldos, setSaldos] = useState({});
  const [loadingSaldos, setLoadingSaldos] = useState(false);
  const [form, setForm] = useState(initialForm);
  const [destinoEditadoManualmente, setDestinoEditadoManualmente] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const { toast, showError, hideToast } = useToast();

  useEffect(() => {
    if (!open) return;
    setFecha(fechaInicial);
    setForm(initialForm);
    setDestinoEditadoManualmente(false);
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
  }, [open, fechaInicial]);

  useEffect(() => {
    if (!open || !fecha) return;
    const loadSaldos = async () => {
      setLoadingSaldos(true);
      try {
        const response = await fetch(`/api/admin/reportes/disponibilidad-cuentas/?fecha=${fecha}`, {
          credentials: 'include',
          cache: 'no-store',
        });
        const data = await response.json();
        if (response.ok && data.ok) {
          const porId = {};
          (data.cuentas || []).forEach((cuenta) => { porId[cuenta.id] = cuenta; });
          setSaldos(porId);
        }
      } catch (error) {
        showError('No se pudo consultar el saldo disponible de las cuentas.');
      } finally {
        setLoadingSaldos(false);
      }
    };
    loadSaldos();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, fecha]);

  const cuentaOrigen = useMemo(() => metodos.find((m) => String(m.id) === String(form.cuenta_origen_id)) || null, [metodos, form.cuenta_origen_id]);
  const cuentaDestino = useMemo(() => metodos.find((m) => String(m.id) === String(form.cuenta_destino_id)) || null, [metodos, form.cuenta_destino_id]);
  const mismaMoneda = cuentaOrigen && cuentaDestino ? cuentaOrigen.moneda === cuentaDestino.moneda : null;

  const saldoBadge = (cuenta) => {
    if (!cuenta) return null;
    const saldo = saldos[cuenta.id];
    if (!saldo) return loadingSaldos ? 'Consultando saldo...' : null;
    if (cuenta.moneda === 'VES') {
      return `Disponible: Bs. ${saldo.saldo_disponible_bs !== null ? formatMonto(saldo.saldo_disponible_bs) : '—'} ($${formatMonto(saldo.saldo_disponible)})`;
    }
    return `Disponible: $${formatMonto(saldo.saldo_disponible)}`;
  };

  const recalcularDestino = (montoOrigen, tasa) => {
    if (destinoEditadoManualmente) return;
    if (!cuentaOrigen || !cuentaDestino || mismaMoneda) return;
    const montoNum = Number(montoOrigen);
    const tasaNum = Number(tasa);
    if (!Number.isFinite(montoNum) || montoNum <= 0 || !Number.isFinite(tasaNum) || tasaNum <= 0) return;
    const destino = cuentaOrigen.moneda === 'VES' ? montoNum / tasaNum : montoNum * tasaNum;
    setForm((current) => ({ ...current, monto_destino: destino.toFixed(2) }));
  };

  const handleField = (field, value) => {
    if (field === 'cuenta_origen_id' || field === 'cuenta_destino_id') {
      setForm((current) => ({ ...current, [field]: value, monto_destino: '', tasa_cambio: '' }));
      setDestinoEditadoManualmente(false);
      return;
    }
    if (field === 'monto_origen' && mismaMoneda) {
      setForm((current) => ({ ...current, monto_origen: value, monto_destino: value }));
      return;
    }
    setForm((current) => ({ ...current, [field]: value }));
    if (field === 'monto_origen') {
      recalcularDestino(value, form.tasa_cambio);
    }
    if (field === 'tasa_cambio') {
      recalcularDestino(form.monto_origen, value);
    }
    if (field === 'monto_destino') {
      setDestinoEditadoManualmente(true);
    }
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!cuentaOrigen || !cuentaDestino) {
      showError('Selecciona la cuenta origen y la cuenta destino.');
      return;
    }
    if (cuentaOrigen.id === cuentaDestino.id) {
      showError('La cuenta origen y la cuenta destino no pueden ser la misma.');
      return;
    }
    if (!form.concepto.trim()) {
      showError('El concepto/motivo es obligatorio.');
      return;
    }
    const montoOrigenNum = Number(form.monto_origen);
    if (!Number.isFinite(montoOrigenNum) || montoOrigenNum <= 0) {
      showError('El monto a debitar debe ser mayor a cero.');
      return;
    }
    if (!mismaMoneda) {
      const tasaNum = Number(form.tasa_cambio);
      if (!Number.isFinite(tasaNum) || tasaNum <= 0) {
        showError('Escribe la tasa acordada para el cruce de monedas.');
        return;
      }
      const montoDestinoNum = Number(form.monto_destino);
      if (!Number.isFinite(montoDestinoNum) || montoDestinoNum <= 0) {
        showError('El monto a recibir debe ser mayor a cero.');
        return;
      }
    }
    const saldoOrigen = saldos[cuentaOrigen.id];
    if (saldoOrigen) {
      const disponible = cuentaOrigen.moneda === 'VES' ? Number(saldoOrigen.saldo_disponible_bs || 0) : Number(saldoOrigen.saldo_disponible);
      if (montoOrigenNum > disponible) {
        showError(`La cuenta origen no tiene saldo disponible suficiente (disponible: ${formatMonto(disponible)}).`);
        return;
      }
    }

    setSubmitting(true);
    try {
      const body = {
        fecha,
        cuenta_origen_id: cuentaOrigen.id,
        cuenta_destino_id: cuentaDestino.id,
        monto_origen: form.monto_origen,
        monto_destino: mismaMoneda ? form.monto_origen : form.monto_destino,
        referencia: form.referencia,
        concepto: form.concepto,
      };
      if (!mismaMoneda) {
        body.tasa_cambio = form.tasa_cambio;
      }
      const response = await fetch('/api/admin/transferencias-cuentas/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo registrar la transferencia.');
      }
      onSuccess(data);
    } catch (error) {
      showError(error.message || 'No se pudo registrar la transferencia.');
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
        <div style={titleStyle}>⇄ Transferencia entre cuentas</div>

        <Toast toast={toast} onClose={hideToast} />

        <form onSubmit={handleSubmit} style={formStyle}>
          <label style={fieldStyle}>
            <span style={labelStyle}>Fecha</span>
            <input
              type="date"
              value={fecha}
              onChange={(event) => setFecha(event.target.value)}
              style={inputStyle}
              required
            />
          </label>

          <div style={columnsStyle}>
            <label style={fieldStyle}>
              <span style={labelStyle}>Cuenta origen (debitar)</span>
              <select
                value={form.cuenta_origen_id}
                onChange={(event) => handleField('cuenta_origen_id', event.target.value)}
                style={inputStyle}
                required
              >
                <option value="">Selecciona...</option>
                {metodos.map((metodo) => (
                  <option key={metodo.id} value={metodo.id}>{metodo.nombre} ({metodo.moneda})</option>
                ))}
              </select>
              {cuentaOrigen ? <div style={saldoBadgeStyle}>{saldoBadge(cuentaOrigen)}</div> : null}
            </label>

            <label style={fieldStyle}>
              <span style={labelStyle}>Cuenta destino (acreditar)</span>
              <select
                value={form.cuenta_destino_id}
                onChange={(event) => handleField('cuenta_destino_id', event.target.value)}
                style={inputStyle}
                required
              >
                <option value="">Selecciona...</option>
                {metodos.map((metodo) => (
                  <option key={metodo.id} value={metodo.id}>{metodo.nombre} ({metodo.moneda})</option>
                ))}
              </select>
              {cuentaDestino ? <div style={saldoBadgeStyle}>{saldoBadge(cuentaDestino)}</div> : null}
            </label>
          </div>

          {cuentaOrigen && cuentaDestino ? (
            mismaMoneda ? (
              <label style={fieldStyle}>
                <span style={labelStyle}>Monto ({cuentaOrigen.moneda})</span>
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  value={form.monto_origen}
                  onChange={(event) => handleField('monto_origen', event.target.value)}
                  style={inputStyle}
                  required
                />
                <div style={hintStyle}>Sale e ingresa exactamente la misma cantidad en ambas cuentas.</div>
              </label>
            ) : (
              <>
                <div style={columnsStyle}>
                  <label style={fieldStyle}>
                    <span style={labelStyle}>Monto a debitar ({cuentaOrigen.moneda})</span>
                    <input
                      type="number"
                      step="0.01"
                      min="0.01"
                      value={form.monto_origen}
                      onChange={(event) => handleField('monto_origen', event.target.value)}
                      style={inputStyle}
                      required
                    />
                  </label>
                  <label style={fieldStyle}>
                    <span style={labelStyle}>Tasa acordada (Bs/USD)</span>
                    <input
                      type="number"
                      step="0.0001"
                      min="0.0001"
                      value={form.tasa_cambio}
                      onChange={(event) => handleField('tasa_cambio', event.target.value)}
                      style={inputStyle}
                      required
                    />
                  </label>
                </div>
                <label style={fieldStyle}>
                  <span style={labelStyle}>Monto a recibir ({cuentaDestino.moneda})</span>
                  <input
                    type="number"
                    step="0.01"
                    min="0.01"
                    value={form.monto_destino}
                    onChange={(event) => handleField('monto_destino', event.target.value)}
                    style={inputStyle}
                    required
                  />
                  <div style={hintStyle}>Se calcula solo con la tasa acordada — ajusta los céntimos si tu banco cobró distinto.</div>
                </label>
              </>
            )
          ) : null}

          <div style={columnsStyle}>
            <label style={fieldStyle}>
              <span style={labelStyle}>Número de referencia (opcional)</span>
              <input
                value={form.referencia}
                onChange={(event) => handleField('referencia', event.target.value)}
                style={inputStyle}
              />
            </label>
            <label style={fieldStyle}>
              <span style={labelStyle}>Concepto / Motivo</span>
              <input
                value={form.concepto}
                onChange={(event) => handleField('concepto', event.target.value)}
                style={inputStyle}
                required
              />
            </label>
          </div>

          <div style={footerStyle}>
            <button type="button" onClick={onClose} style={cancelButtonStyle} disabled={submitting}>
              Cancelar
            </button>
            <button type="submit" style={confirmButtonStyle} disabled={submitting}>
              {submitting ? 'Procesando...' : 'Transferir'}
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
  maxWidth: 560,
  maxHeight: '90vh',
  overflowY: 'auto',
  borderRadius: 20,
  border: '1px solid rgba(150, 145, 255, 0.3)',
  background: 'linear-gradient(180deg, rgba(16, 12, 28, 0.98) 0%, rgba(8, 8, 10, 0.99) 100%)',
  padding: '22px 22px 18px',
  boxShadow: '0 20px 50px rgba(0, 0, 0, 0.45)',
};

const titleStyle = {
  color: '#fff',
  fontSize: 19,
  fontWeight: 800,
  marginBottom: 14,
};

const formStyle = { display: 'grid', gap: 14 };
const columnsStyle = { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 };
const fieldStyle = { display: 'grid', gap: 6 };
const labelStyle = { color: '#c9b8ff', fontSize: 12.5, fontWeight: 700 };
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
const hintStyle = { margin: 0, color: '#a89999', fontSize: 11.5 };
const saldoBadgeStyle = { color: '#bdd0ff', fontSize: 11.5, fontWeight: 700 };

const footerStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  gap: 10,
  marginTop: 6,
  flexWrap: 'wrap',
};

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
  background: 'linear-gradient(90deg, #6d28d9 0%, #4f46e5 100%)',
  color: '#fff',
  fontWeight: 700,
  cursor: 'pointer',
  boxShadow: '0 8px 20px rgba(79, 70, 229, 0.35)',
};

export default TransferenciaCuentasModal;
