import { useCallback, useEffect, useMemo, useState } from 'react';
import BotonDescargarPdf from './BotonDescargarPdf';
import Toast from './Toast';
import MoneyInput from './MoneyInput';
import useToast from '../hooks/useToast';
import { formatFecha, formatMonto } from '../utils/lotesPos';

function isoLocal(fecha) {
  const local = new Date(fecha.getTime() - fecha.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

// Rango por defecto: la semana anterior (lunes a domingo), que es la que cubre
// el reporte de Cashea; la administradora puede cambiar cualquiera de las dos fechas.
function rangoSemanaAnterior() {
  const hoy = new Date();
  hoy.setHours(12, 0, 0, 0);
  const diasDesdeLunes = (hoy.getDay() + 6) % 7;
  const lunes = new Date(hoy);
  lunes.setDate(hoy.getDate() - diasDesdeLunes - 7);
  const domingo = new Date(lunes);
  domingo.setDate(lunes.getDate() + 6);
  return { desde: isoLocal(lunes), hasta: isoLocal(domingo) };
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
// liquidar) y el registro de su pago semanal. Cashea entrega un reporte por
// periodo y paga cualquier día después: se elige el rango de fechas del
// reporte, se teclean sus dos totales y Sevens exige que su suma de ese rango
// coincida con el «Monto financiado» antes de registrar.
function CasheaPage({ isMobile, onBack }) {
  const { toast, showSuccess, showError, hideToast } = useToast();
  const [loading, setLoading] = useState(true);
  const [pendientes, setPendientes] = useState(null);
  const [liquidaciones, setLiquidaciones] = useState({ liquidaciones: [], totales: null });
  const [cuentasBs, setCuentasBs] = useState([]);
  const [rango, setRango] = useState(() => rangoSemanaAnterior());
  const [excluidos, setExcluidos] = useState(() => new Set());
  const [saving, setSaving] = useState(false);

  const [cuentaDestinoId, setCuentaDestinoId] = useState('');
  const [fechaDeposito, setFechaDeposito] = useState(isoLocal(new Date()));
  const [depositoBs, setDepositoBs] = useState('');
  const [financiadoReporte, setFinanciadoReporte] = useState('');
  const [totalPagar, setTotalPagar] = useState('');
  const [ajuste, setAjuste] = useState('');
  const [referencia, setReferencia] = useState('');

  const rangoValido = Boolean(rango.desde && rango.hasta && rango.desde <= rango.hasta);
  const etiquetaRango = rangoValido
    ? `${formatFecha(rango.desde)} al ${formatFecha(rango.hasta)}`
    : 'rango sin definir';

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
      setExcluidos(new Set());
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

  const todos = pendientes?.pendientes || [];
  const deLaSemana = useMemo(
    () => (rangoValido ? todos.filter((item) => item.fecha >= rango.desde && item.fecha <= rango.hasta) : []),
    [todos, rango, rangoValido],
  );
  const fueraDeLaSemana = todos.length - deLaSemana.length;
  const incluidos = deLaSemana.filter((item) => !excluidos.has(item.pago_id));
  const sumaSevens = incluidos.reduce((acc, item) => acc + Number(item.monto_usd), 0);
  const sumaBsRegistro = incluidos.reduce((acc, item) => acc + Number(item.monto_bs_registro || 0), 0);
  const sumaBsActual = incluidos.reduce((acc, item) => acc + Number(item.monto_bs_actual || 0), 0);
  const tasaActual = Number(pendientes?.tasa_actual) || null;

  const reporteNum = Number(financiadoReporte) || 0;
  const diferencia = reporteNum - sumaSevens;
  const cuadra = reporteNum > 0 && Math.abs(diferencia) <= 0.01;
  const totalNum = Number(totalPagar) || 0;
  const depositoNum = Number(depositoBs) || 0;
  const tasaImplicita = totalNum > 0 && depositoNum > 0 ? depositoNum / totalNum : null;
  const comision = totalNum > 0 ? sumaSevens - Number(ajuste || 0) - totalNum : null;

  const alternar = (pagoId) => {
    setExcluidos((actual) => {
      const copia = new Set(actual);
      if (copia.has(pagoId)) {
        copia.delete(pagoId);
      } else {
        copia.add(pagoId);
      }
      return copia;
    });
  };

  const registrar = async (event) => {
    event.preventDefault();
    if (!rangoValido) {
      showError('Indica el rango de fechas del reporte de Cashea (desde no puede ser posterior a hasta).');
      return;
    }
    if (incluidos.length === 0) {
      showError('No hay cobros de Cashea en ese rango para liquidar.');
      return;
    }
    if (!cuentaDestinoId) {
      showError('Elige la cuenta en bolívares donde cayó el depósito.');
      return;
    }
    if (!(depositoNum > 0) || !(totalNum > 0) || !(reporteNum > 0)) {
      showError('Completa los bolívares depositados y los dos totales del reporte de Cashea.');
      return;
    }
    if (!cuadra) {
      showError(`No cuadra con el reporte: Sevens suma $${formatMonto(sumaSevens)} y el reporte indica $${formatMonto(reporteNum)}.`);
      return;
    }
    if (comision !== null && comision < 0) {
      showError('El «Total a pagar» es mayor a lo financiado. Revisa los totales del reporte.');
      return;
    }
    setSaving(true);
    try {
      const json = await pedir('/api/admin/cashea/liquidaciones/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'registrar',
          periodo_desde: rango.desde,
          periodo_hasta: rango.hasta,
          pago_ids: incluidos.map((item) => item.pago_id),
          cuenta_destino_id: Number(cuentaDestinoId),
          deposito_bs: depositoBs,
          monto_financiado_reporte: financiadoReporte,
          total_pagar_usd: totalPagar,
          ajuste_cancelaciones_usd: ajuste || '0',
          fecha_deposito: fechaDeposito,
          referencia: referencia.trim(),
        }),
      });
      showSuccess(json.message);
      setDepositoBs('');
      setFinanciadoReporte('');
      setTotalPagar('');
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
          Lo que financia Cashea no es dinero disponible hasta que Cashea paga. Elige el rango de fechas que
          cubre el reporte, teclea sus totales y la fecha en que depositó: el total de Sevens tiene que
          coincidir con el del reporte. El banco sube por lo depositado y la comisión queda como gasto aparte.
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
              {pendientes.por_cobrar_bs_actual ? (
                <span style={mutedStyle}>
                  Bs {formatMonto(pendientes.por_cobrar_bs_actual)} a la tasa actual (Bs {formatMonto(pendientes.tasa_actual)})
                </span>
              ) : null}
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
            <div style={sectionTitleStyle}>Rango del reporte de Cashea</div>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'end' }}>
              <label style={{ ...fieldStyle, minWidth: 170 }}>
                <span>Desde</span>
                <input
                  type="date"
                  value={rango.desde}
                  onChange={(event) => { setRango((actual) => ({ ...actual, desde: event.target.value })); setExcluidos(new Set()); }}
                  style={inputStyle}
                />
              </label>
              <label style={{ ...fieldStyle, minWidth: 170 }}>
                <span>Hasta</span>
                <input
                  type="date"
                  value={rango.hasta}
                  onChange={(event) => { setRango((actual) => ({ ...actual, hasta: event.target.value })); setExcluidos(new Set()); }}
                  style={inputStyle}
                />
              </label>
            </div>
            {!rangoValido ? (
              <div style={noticeStyle}>Indica las dos fechas; «Desde» no puede ser posterior a «Hasta».</div>
            ) : (
              <div>
                <BotonDescargarPdf
                  url="/api/admin/reportes/cashea-por-cobrar-pdf/"
                  params={{ desde: rango.desde, hasta: rango.hasta }}
                  onError={showError}
                >
                  Descargar PDF de lo que nos debe Cashea
                </BotonDescargarPdf>
              </div>
            )}

            {deLaSemana.length === 0 ? (
              <div style={emptyStyle}>No hay cobros de Cashea sin liquidar en ese rango.</div>
            ) : (
              <div style={tableWrapStyle}>
                <div style={pendientesTableStyle}>
                  <div style={headStyle}>Incluir</div>
                  <div style={headStyle}>Orden Cashea</div>
                  <div style={headStyle}>Fecha</div>
                  <div style={headStyle}>Nota</div>
                  <div style={headStyle}>Cliente</div>
                  <div style={{ ...headStyle, textAlign: 'right' }}>Monto $</div>
                  <div style={{ ...headStyle, textAlign: 'right' }}>Tasa de registro</div>
                  <div style={{ ...headStyle, textAlign: 'right' }}>Bs a esa tasa</div>
                  <div style={{ ...headStyle, textAlign: 'right' }}>Tasa actual</div>
                  <div style={{ ...headStyle, textAlign: 'right' }}>Debería pagar en Bs (tasa actual)</div>
                  {deLaSemana.map((item) => (
                    <div key={item.pago_id} style={{ display: 'contents' }}>
                      <div style={cellStyle}>
                        <input type="checkbox" checked={!excluidos.has(item.pago_id)} onChange={() => alternar(item.pago_id)} />
                      </div>
                      <div style={{ ...cellStyle, fontWeight: 700 }}>{item.orden_cashea}</div>
                      <div style={cellStyle}>{formatFecha(item.fecha)}</div>
                      <div style={cellStyle}>
                        {item.nota_codigo}
                        {item.nota_estado === 'anulada' ? <span style={{ ...mutedStyle, color: 'var(--vg-f-ffb0b0)' }}>Nota anulada</span> : null}
                      </div>
                      <div style={cellStyle}>{item.cliente || '—'}</div>
                      <div style={{ ...cellStyle, textAlign: 'right', fontWeight: 700 }}>${formatMonto(item.monto_usd)}</div>
                      <div style={{ ...cellStyle, textAlign: 'right' }}>{item.tasa_registro ? formatMonto(item.tasa_registro) : '—'}</div>
                      <div style={{ ...cellStyle, textAlign: 'right' }}>{item.monto_bs_registro ? `Bs ${formatMonto(item.monto_bs_registro)}` : '—'}</div>
                      <div style={{ ...cellStyle, textAlign: 'right' }}>{item.tasa_actual ? formatMonto(item.tasa_actual) : '—'}</div>
                      <div style={{ ...cellStyle, textAlign: 'right', fontWeight: 700 }}>{item.monto_bs_actual ? `Bs ${formatMonto(item.monto_bs_actual)}` : '—'}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {deLaSemana.length > 0 ? (
              <div style={calculoBoxStyle}>
                <div style={calculoFilaStyle}>
                  <span>Seleccionados ({incluidos.length} cobro(s)) — deuda en dólares</span>
                  <strong>${formatMonto(sumaSevens)}</strong>
                </div>
                <div style={calculoFilaStyle}>
                  <span>Equivale a la tasa en que se registró cada cobro</span>
                  <strong>Bs {formatMonto(sumaBsRegistro)}</strong>
                </div>
                <div style={{ ...calculoFilaStyle, color: 'var(--vg-f-ffcf7d)' }}>
                  <span>Cashea debería pagar a la tasa actual{tasaActual ? ` (Bs ${formatMonto(tasaActual)})` : ''}</span>
                  <strong>{tasaActual ? `Bs ${formatMonto(sumaBsActual)}` : '—'}</strong>
                </div>
              </div>
            ) : null}
            {fueraDeLaSemana > 0 ? (
              <div style={mutedStyle}>
                Hay {fueraDeLaSemana} cobro(s) sin liquidar fuera de este rango; no entran en este pago.
              </div>
            ) : null}
          </section>

          {deLaSemana.length > 0 ? (
            <form onSubmit={registrar} style={panelStyle}>
              <div style={sectionTitleStyle}>Pago de Cashea del {etiquetaRango}</div>

              <div style={formGridStyle(isMobile)}>
                <label style={fieldStyle}>
                  <span>Fecha en que depositó Cashea</span>
                  <input type="date" value={fechaDeposito} onChange={(event) => setFechaDeposito(event.target.value)} style={inputStyle} />
                </label>
                <label style={fieldStyle}>
                  <span>Cuenta donde cayó (Bs)</span>
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
                  <span>«Monto financiado» del reporte ($)</span>
                  <MoneyInput value={financiadoReporte} onChange={setFinanciadoReporte} placeholder="0.00" style={inputStyle} />
                </label>
                <label style={fieldStyle}>
                  <span>«Total a pagar» del reporte ($)</span>
                  <MoneyInput value={totalPagar} onChange={setTotalPagar} placeholder="0.00" style={inputStyle} />
                </label>
                <label style={fieldStyle}>
                  <span>Financiado de órdenes canceladas ($, opcional)</span>
                  <MoneyInput value={ajuste} onChange={setAjuste} placeholder="0.00" style={inputStyle} />
                </label>
                <label style={fieldStyle}>
                  <span>Referencia del depósito</span>
                  <input type="text" value={referencia} onChange={(event) => setReferencia(event.target.value)} placeholder="Opcional" style={inputStyle} />
                </label>
              </div>

              <div style={calculoBoxStyle}>
                <div style={calculoFilaStyle}>
                  <span>Sevens suma ({incluidos.length} cobro(s))</span>
                  <strong>${formatMonto(sumaSevens)}</strong>
                </div>
                <div style={calculoFilaStyle}>
                  <span>Reporte de Cashea</span>
                  <strong>{reporteNum > 0 ? `$${formatMonto(reporteNum)}` : '—'}</strong>
                </div>
                <div
                  style={{
                    ...calculoFilaStyle,
                    color: reporteNum <= 0 ? 'var(--vg-f-c8bbbb)' : (cuadra ? 'var(--vg-f-8fffb0)' : 'var(--vg-f-ff9d9d)'),
                  }}
                >
                  <span>Estado</span>
                  <strong>
                    {reporteNum <= 0
                      ? 'Falta el monto financiado del reporte'
                      : (cuadra ? 'Coincide con el reporte ✓' : `No cuadra: diferencia $${formatMonto(diferencia)}`)}
                  </strong>
                </div>
                <div style={calculoFilaStyle}>
                  <span>Tasa que usó Cashea (Bs ÷ total a pagar)</span>
                  <strong>{tasaImplicita !== null ? `Bs ${formatMonto(tasaImplicita)}` : '—'}</strong>
                </div>
                <div style={{ ...calculoFilaStyle, color: comision !== null && comision < 0 ? 'var(--vg-f-ff9d9d)' : 'var(--vg-f-ffcf7d)' }}>
                  <span>Comisión de Cashea (gasto)</span>
                  <strong>
                    {comision !== null ? `$${formatMonto(comision)}` : '—'}
                    {comision !== null && sumaSevens > 0 ? ` · ${((comision / sumaSevens) * 100).toFixed(2)}%` : ''}
                  </strong>
                </div>
              </div>

              <button type="submit" style={primaryButtonStyle} disabled={saving || !cuadra}>
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
                  <div style={headStyle}>Rango / depósito</div>
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
                        {item.periodo_desde && item.periodo_hasta
                          ? `Del ${formatFecha(item.periodo_desde)} al ${formatFecha(item.periodo_hasta)}`
                          : 'Rango sin indicar'}
                        <span style={mutedStyle}>
                          Pagó {formatFecha(item.fecha_deposito)} · Bs {formatMonto(item.deposito_bs)} a {formatMonto(item.tasa_cambio)}
                        </span>
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
const pendientesTableStyle = { display: 'grid', gridTemplateColumns: '64px minmax(120px,1fr) minmax(95px,0.7fr) minmax(100px,0.7fr) minmax(140px,1.1fr) minmax(90px,0.6fr) minmax(100px,0.7fr) minmax(130px,0.9fr) minmax(100px,0.7fr) minmax(150px,1fr)', minWidth: 1180, border: '1px solid rgba(var(--vg-ink), 0.08)', borderRadius: 14, overflow: 'hidden' };
const historialTableStyle = { display: 'grid', gridTemplateColumns: 'minmax(130px,1fr) minmax(220px,1.4fr) minmax(130px,1fr) minmax(110px,0.8fr) minmax(110px,0.8fr) minmax(150px,1fr)', minWidth: 880, border: '1px solid rgba(var(--vg-ink), 0.08)', borderRadius: 14, overflow: 'hidden' };
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
