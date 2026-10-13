import { useCallback, useEffect, useMemo, useState } from 'react';
import Toast from './Toast';
import MoneyInput from './MoneyInput';
import useToast from '../hooks/useToast';
import useExchangeRate from '../hooks/useExchangeRate';
import { formatFecha, formatMonto } from '../utils/lotesPos';

function todayIso() {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

async function pedir(url, opciones) {
  const response = await fetch(url, { credentials: 'include', cache: 'no-store', ...opciones });
  const json = await response.json().catch(() => ({}));
  if (!response.ok || !json.ok) {
    throw new Error(json.message || 'No se pudo completar la operación.');
  }
  return json;
}

// Cashea: lo que Cashea nos debe (cobros con la cuenta Cashea todavía sin
// liquidar) y el registro de su pago semanal en bolívares a la tasa del día.
function CasheaPage({ isMobile, onBack }) {
  const tasaBcv = useExchangeRate();
  const { toast, showSuccess, showError, hideToast } = useToast();
  const [loading, setLoading] = useState(true);
  const [pendientes, setPendientes] = useState(null);
  const [liquidaciones, setLiquidaciones] = useState({ liquidaciones: [], totales: null });
  const [cuentasBs, setCuentasBs] = useState([]);
  const [seleccion, setSeleccion] = useState(() => new Set());
  const [saving, setSaving] = useState(false);

  const [cuentaDestinoId, setCuentaDestinoId] = useState('');
  const [depositoBs, setDepositoBs] = useState('');
  const [tasa, setTasa] = useState('');
  const [ajuste, setAjuste] = useState('');
  const [fechaDeposito, setFechaDeposito] = useState(todayIso());
  const [referencia, setReferencia] = useState('');

  const cargar = useCallback(async () => {
    setLoading(true);
    try {
      const [p, l, m] = await Promise.all([
        pedir('/api/admin/cashea/pendientes/'),
        pedir('/api/admin/cashea/liquidaciones/'),
        pedir('/api/metodos-pago/'),
      ]);
      setPendientes(p);
      setLiquidaciones(l);
      setCuentasBs((m.metodos_pago || []).filter((metodo) => metodo.moneda === 'VES' && !metodo.es_cashea));
      setSeleccion(new Set());
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

  useEffect(() => {
    if (!tasa && tasaBcv) {
      setTasa(String(tasaBcv));
    }
  }, [tasaBcv, tasa]);

  const lista = pendientes?.pendientes || [];
  const financiado = useMemo(
    () => lista.filter((item) => seleccion.has(item.pago_id)).reduce((acc, item) => acc + Number(item.monto_usd), 0),
    [lista, seleccion],
  );
  const neto = Number(tasa) > 0 && Number(depositoBs) > 0 ? Number(depositoBs) / Number(tasa) : null;
  const comision = neto !== null ? financiado - Number(ajuste || 0) - neto : null;

  const alternar = (pagoId) => {
    setSeleccion((actual) => {
      const copia = new Set(actual);
      if (copia.has(pagoId)) {
        copia.delete(pagoId);
      } else {
        copia.add(pagoId);
      }
      return copia;
    });
  };

  const alternarTodos = () => {
    setSeleccion((actual) => (actual.size === lista.length ? new Set() : new Set(lista.map((item) => item.pago_id))));
  };

  const registrar = async (event) => {
    event.preventDefault();
    if (seleccion.size === 0) {
      showError('Selecciona los cobros de Cashea que incluye este pago.');
      return;
    }
    if (!cuentaDestinoId) {
      showError('Elige la cuenta en bolívares donde cayó el depósito.');
      return;
    }
    if (!(Number(depositoBs) > 0)) {
      showError('Indica los bolívares que depositó Cashea.');
      return;
    }
    if (!(Number(tasa) > 0)) {
      showError('Indica la tasa del día con la que Cashea convirtió.');
      return;
    }
    if (comision !== null && comision < 0) {
      showError('El depósito en dólares es mayor a lo financiado. Revisa los bolívares, la tasa y los cobros.');
      return;
    }
    setSaving(true);
    try {
      const json = await pedir('/api/admin/cashea/liquidaciones/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'registrar',
          pago_ids: Array.from(seleccion),
          cuenta_destino_id: Number(cuentaDestinoId),
          deposito_bs: depositoBs,
          tasa_cambio: tasa,
          ajuste_cancelaciones_usd: ajuste || '0',
          fecha_deposito: fechaDeposito,
          referencia: referencia.trim(),
        }),
      });
      showSuccess(json.message);
      setDepositoBs('');
      setAjuste('');
      setReferencia('');
      await cargar();
    } catch (error) {
      showError(error.message);
    } finally {
      setSaving(false);
    }
  };

  const anular = async (liquidacion) => {
    const motivo = window.prompt(`¿Anular la liquidación ${liquidacion.codigo}? Sus cobros vuelven a estar por cobrar. Indica el motivo:`);
    if (!motivo || !motivo.trim()) {
      return;
    }
    try {
      const json = await pedir('/api/admin/cashea/liquidaciones/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'anular', id: liquidacion.id, motivo: motivo.trim() }),
      });
      showSuccess(json.message);
      await cargar();
    } catch (error) {
      showError(error.message);
    }
  };

  const sinCuenta = !loading && pendientes && !pendientes.cuenta_cashea;

  return (
    <div style={containerStyle(isMobile)}>
      <Toast toast={toast} onClose={hideToast} />
      <button type="button" onClick={onBack} style={backButtonStyle}>← Volver a Contabilidad</button>
      <div>
        <h2 style={titleStyle(isMobile)}>Cashea</h2>
        <p style={subtitleStyle}>
          Lo que financia Cashea no es dinero disponible hasta que Cashea paga la semana. Aquí ves lo que
          Cashea nos debe y registras su depósito en bolívares: el banco sube por lo depositado y la
          comisión queda como gasto aparte.
        </p>
      </div>

      {loading ? <div style={emptyStyle}>Cargando...</div> : null}

      {sinCuenta ? (
        <div style={noticeStyle}>
          Aún no hay una cuenta de Cashea. En Métodos de pago crea un método en dólares (por ejemplo «Cashea»)
          y márcalo en la columna «Cashea».
        </div>
      ) : null}

      {!loading && pendientes && pendientes.cuenta_cashea ? (
        <>
          <section style={resumenGridStyle(isMobile)}>
            <div style={resumenCardStyle}>
              <span style={sectionLabelStyle}>Por cobrar a Cashea</span>
              <span style={resumenValorStyle}>${formatMonto(pendientes.por_cobrar_usd)}</span>
              <span style={mutedStyle}>{pendientes.cantidad} cobro(s) sin liquidar</span>
            </div>
            <div style={resumenCardStyle}>
              <span style={sectionLabelStyle}>Cobrado por Cashea (histórico)</span>
              <span style={resumenValorStyle}>${formatMonto(liquidaciones.totales?.neto_usd)}</span>
              <span style={mutedStyle}>Bs {formatMonto(liquidaciones.totales?.deposito_bs)} depositados</span>
            </div>
            <div style={resumenCardStyle}>
              <span style={sectionLabelStyle}>Comisión pagada a Cashea</span>
              <span style={resumenValorStyle}>${formatMonto(liquidaciones.totales?.comision_usd)}</span>
              <span style={mutedStyle}>
                {Number(liquidaciones.totales?.financiado_usd) > 0
                  ? `${((Number(liquidaciones.totales.comision_usd) / Number(liquidaciones.totales.financiado_usd)) * 100).toFixed(2)}% de lo financiado`
                  : 'Aún sin liquidaciones'}
              </span>
            </div>
          </section>

          <section style={panelStyle}>
            <div style={sectionTitleStyle}>Cobros pendientes de liquidar</div>
            {lista.length === 0 ? (
              <div style={emptyStyle}>Cashea no nos debe nada ahora mismo.</div>
            ) : (
              <div style={tableWrapStyle}>
                <div style={pendientesTableStyle}>
                  <div style={headStyle}>
                    <input type="checkbox" checked={seleccion.size === lista.length} onChange={alternarTodos} aria-label="Seleccionar todos" />
                  </div>
                  <div style={headStyle}>Orden Cashea</div>
                  <div style={headStyle}>Fecha</div>
                  <div style={headStyle}>Nota</div>
                  <div style={headStyle}>Cliente</div>
                  <div style={{ ...headStyle, textAlign: 'right' }}>Monto</div>
                  {lista.map((item) => (
                    <div key={item.pago_id} style={{ display: 'contents' }}>
                      <div style={cellStyle}>
                        <input type="checkbox" checked={seleccion.has(item.pago_id)} onChange={() => alternar(item.pago_id)} />
                      </div>
                      <div style={{ ...cellStyle, fontWeight: 700 }}>{item.orden_cashea}</div>
                      <div style={cellStyle}>
                        {formatFecha(item.fecha)}
                        <span style={mutedStyle}>{item.dias === 0 ? 'hoy' : `hace ${item.dias} d`}</span>
                      </div>
                      <div style={cellStyle}>
                        {item.nota_codigo}
                        {item.nota_estado === 'anulada' ? <span style={{ ...mutedStyle, color: 'var(--vg-f-ffb0b0)' }}>Nota anulada</span> : null}
                      </div>
                      <div style={cellStyle}>{item.cliente || '—'}</div>
                      <div style={{ ...cellStyle, textAlign: 'right', fontWeight: 700 }}>${formatMonto(item.monto_usd)}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>

          {lista.length > 0 ? (
            <form onSubmit={registrar} style={panelStyle}>
              <div style={sectionTitleStyle}>Registrar depósito de Cashea</div>
              <div style={mutedStyle}>
                Selecciona arriba los cobros que incluye el pago del reporte semanal. Seleccionados:{' '}
                {seleccion.size} · ${formatMonto(financiado)} financiado.
              </div>

              <div style={formGridStyle(isMobile)}>
                <label style={fieldStyle}>
                  <span>Cuenta donde cayó el depósito (Bs)</span>
                  <select
                    value={cuentaDestinoId}
                    onChange={(event) => setCuentaDestinoId(event.target.value)}
                    style={inputStyle}
                    className="admin-dark-select"
                  >
                    <option value="">Selecciona una cuenta...</option>
                    {cuentasBs.map((cuenta) => (
                      <option key={cuenta.id} value={cuenta.id}>{cuenta.nombre}</option>
                    ))}
                  </select>
                </label>
                <label style={fieldStyle}>
                  <span>Bolívares depositados</span>
                  <MoneyInput value={depositoBs} onChange={setDepositoBs} placeholder="Bs depositados" style={inputStyle} />
                </label>
                <label style={fieldStyle}>
                  <span>Tasa del día (Bs por $)</span>
                  <MoneyInput value={tasa} onChange={setTasa} maxDecimales={4} placeholder="Tasa" style={inputStyle} />
                </label>
                <label style={fieldStyle}>
                  <span>Ajuste por cancelaciones ($, opcional)</span>
                  <MoneyInput value={ajuste} onChange={setAjuste} placeholder="0.00" style={inputStyle} />
                </label>
                <label style={fieldStyle}>
                  <span>Fecha del depósito</span>
                  <input type="date" value={fechaDeposito} onChange={(event) => setFechaDeposito(event.target.value)} style={inputStyle} />
                </label>
                <label style={fieldStyle}>
                  <span>Referencia del depósito</span>
                  <input type="text" value={referencia} onChange={(event) => setReferencia(event.target.value)} placeholder="Opcional" style={inputStyle} />
                </label>
              </div>

              <div style={calculoBoxStyle}>
                <div style={calculoFilaStyle}><span>Financiado seleccionado</span><strong>${formatMonto(financiado)}</strong></div>
                <div style={calculoFilaStyle}>
                  <span>(−) Ajuste por cancelaciones</span><strong>${formatMonto(ajuste || 0)}</strong>
                </div>
                <div style={calculoFilaStyle}>
                  <span>Depositado en dólares (Bs ÷ tasa)</span>
                  <strong>{neto !== null ? `$${formatMonto(neto)}` : '—'}</strong>
                </div>
                <div style={{ ...calculoFilaStyle, color: comision !== null && comision < 0 ? 'var(--vg-f-ff9d9d)' : 'var(--vg-f-ffcf7d)' }}>
                  <span>Comisión de Cashea (gasto)</span>
                  <strong>
                    {comision !== null ? `$${formatMonto(comision)}` : '—'}
                    {comision !== null && financiado > 0 ? ` · ${((comision / financiado) * 100).toFixed(2)}%` : ''}
                  </strong>
                </div>
              </div>

              <button type="submit" style={primaryButtonStyle} disabled={saving || seleccion.size === 0}>
                {saving ? 'Registrando...' : 'Registrar liquidación'}
              </button>
            </form>
          ) : null}

          <section style={panelStyle}>
            <div style={sectionTitleStyle}>Liquidaciones registradas</div>
            {liquidaciones.liquidaciones.length === 0 ? (
              <div style={emptyStyle}>Aún no hay liquidaciones.</div>
            ) : (
              <div style={tableWrapStyle}>
                <div style={historialTableStyle}>
                  <div style={headStyle}>Código</div>
                  <div style={headStyle}>Depósito</div>
                  <div style={headStyle}>Cuenta</div>
                  <div style={{ ...headStyle, textAlign: 'right' }}>Financiado</div>
                  <div style={{ ...headStyle, textAlign: 'right' }}>Comisión</div>
                  <div style={headStyle}>Estado</div>
                  {liquidaciones.liquidaciones.map((item) => (
                    <div key={item.id} style={{ display: 'contents' }}>
                      <div style={{ ...cellStyle, fontWeight: 700 }}>
                        {item.codigo}
                        <span style={mutedStyle}>{item.referencia || 'Sin referencia'}</span>
                      </div>
                      <div style={cellStyle}>
                        {formatFecha(item.fecha_deposito)}
                        <span style={mutedStyle}>Bs {formatMonto(item.deposito_bs)} a {formatMonto(item.tasa_cambio)}</span>
                      </div>
                      <div style={cellStyle}>{item.cuenta_destino}</div>
                      <div style={{ ...cellStyle, textAlign: 'right' }}>${formatMonto(item.monto_financiado_usd)}</div>
                      <div style={{ ...cellStyle, textAlign: 'right' }}>
                        ${formatMonto(item.comision_usd)}
                        {item.comision_pct_financiado ? <span style={mutedStyle}>{item.comision_pct_financiado}%</span> : null}
                      </div>
                      <div style={cellStyle}>
                        {item.estado === 'anulada' ? (
                          <span style={{ ...badgeStyle, color: '#c8bbbb', background: 'rgba(255,255,255,0.08)' }}>Anulada</span>
                        ) : (
                          <>
                            <span style={{ ...badgeStyle, color: '#bdf0cf', background: 'rgba(70,200,120,0.16)' }}>Registrada</span>
                            <button type="button" style={miniDangerStyle} onClick={() => anular(item)}>Anular</button>
                          </>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>
        </>
      ) : null}
    </div>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const titleStyle = (isMobile) => ({ margin: 0, color: 'var(--vg-text-strong)', fontSize: isMobile ? 28 : 34 });
const subtitleStyle = { margin: '8px 0 0', color: 'var(--vg-f-d2c3c3)', maxWidth: 720, lineHeight: 1.6 };
const panelStyle = { display: 'grid', gap: 14, padding: 18, borderRadius: 20, border: '1px solid rgba(var(--vg-ink), 0.1)', background: 'linear-gradient(180deg, var(--vg-bg-card) 0%, var(--vg-s-080808-a980) 100%)' };
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(var(--vg-ink), 0.12)', color: 'var(--vg-f-c8bbbb)' };
const noticeStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid var(--vg-f-ff9191-a220)', background: 'rgba(255,98,98,0.12)', color: 'var(--vg-f-ffd8d8)' };
const sectionTitleStyle = { color: 'var(--vg-text-strong)', fontSize: 18, fontWeight: 800 };
const sectionLabelStyle = { color: 'var(--vg-f-ffb0b0)', fontSize: 11.5, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.06em' };
const mutedStyle = { color: 'var(--vg-f-a89999)', fontSize: 12, display: 'block' };
const resumenGridStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, 1fr)', gap: 12 });
const resumenCardStyle = { display: 'grid', gap: 6, padding: 16, borderRadius: 16, border: '1px solid rgba(var(--vg-ink), 0.1)', background: 'rgba(var(--vg-ink), 0.03)' };
const resumenValorStyle = { color: 'var(--vg-text-strong)', fontSize: 26, fontWeight: 800 };
const tableWrapStyle = { overflowX: 'auto' };
const pendientesTableStyle = { display: 'grid', gridTemplateColumns: '48px minmax(130px,1fr) minmax(110px,0.8fr) minmax(110px,0.8fr) minmax(150px,1.2fr) minmax(100px,0.7fr)', minWidth: 720, border: '1px solid rgba(var(--vg-ink), 0.08)', borderRadius: 14, overflow: 'hidden' };
const historialTableStyle = { display: 'grid', gridTemplateColumns: 'minmax(130px,1fr) minmax(180px,1.2fr) minmax(130px,1fr) minmax(110px,0.8fr) minmax(110px,0.8fr) minmax(150px,1fr)', minWidth: 820, border: '1px solid rgba(var(--vg-ink), 0.08)', borderRadius: 14, overflow: 'hidden' };
const headStyle = { padding: '12px 14px', background: 'rgba(var(--vg-ink), 0.06)', color: 'var(--vg-f-ffb0b0)', fontSize: 12, letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 800 };
const cellStyle = { padding: '12px 14px', borderTop: '1px solid rgba(var(--vg-ink), 0.08)', color: 'var(--vg-f-f2e6e6)', display: 'grid', alignContent: 'center', gap: 2 };
const formGridStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, minmax(0, 1fr))', gap: 12 });
const fieldStyle = { display: 'grid', gap: 6, color: 'var(--vg-f-f2e6e6)', fontSize: 13, fontWeight: 700 };
const inputStyle = { borderRadius: 12, border: '1px solid rgba(var(--vg-ink), 0.14)', background: 'var(--vg-s-161010)', padding: '10px 12px', color: 'var(--vg-text-strong)', width: '100%', boxSizing: 'border-box' };
const calculoBoxStyle = { display: 'grid', gap: 8, padding: 14, borderRadius: 14, border: '1px solid var(--vg-f-ffcf85-a350)', background: 'rgba(255,207,133,0.05)' };
const calculoFilaStyle = { display: 'flex', justifyContent: 'space-between', gap: 12, color: 'var(--vg-f-f2e6e6)' };
const badgeStyle = { fontSize: 11, fontWeight: 800, padding: '3px 10px', borderRadius: 999, textTransform: 'uppercase', letterSpacing: '0.04em', width: 'fit-content' };
const miniDangerStyle = { border: '1px solid var(--vg-f-ff7e7e-a400)', borderRadius: 999, padding: '6px 12px', background: 'rgba(145,33,33,0.25)', color: 'var(--vg-f-ffd3d3)', fontWeight: 700, cursor: 'pointer', fontSize: 12.5, width: 'fit-content' };
const primaryButtonStyle = { border: 'none', borderRadius: 999, padding: '12px 18px', background: 'linear-gradient(90deg, #bf1f1f 0%, var(--vg-accent-primary) 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', width: 'fit-content' };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };

export default CasheaPage;
