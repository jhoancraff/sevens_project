import { Fragment, useCallback, useEffect, useState } from 'react';
import ActionMenuSelect from './ActionMenuSelect';
import IngresoNoFacturadoModal from './IngresoNoFacturadoModal';
import Toast from './Toast';
import TransferenciaCuentasModal from './TransferenciaCuentasModal';
import useToast from '../hooks/useToast';
import { DiaFecha } from './FiltroFechas';

function todayIso() {
  const now = new Date();
  const offset = now.getTimezoneOffset();
  const local = new Date(now.getTime() - offset * 60000);
  return local.toISOString().slice(0, 10);
}

function formatMonto(value) {
  const number = Number(value || 0);
  return number.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function ReporteDisponibilidadCuentasPage({ isMobile, onBack, onViewHistorialTransferencias, onViewHistorialIngresos, onNavigate }) {
  const [fecha, setFecha] = useState(todayIso());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [transferenciaModalOpen, setTransferenciaModalOpen] = useState(false);
  const [ingresoModalOpen, setIngresoModalOpen] = useState(false);
  const { toast, showSuccess, hideToast } = useToast();

  const loadReport = useCallback(async (fechaConsultada) => {
    setLoading(true);
    setError('');
    try {
      const response = await fetch(`/api/admin/reportes/disponibilidad-cuentas/?fecha=${fechaConsultada}`, {
        credentials: 'include',
        cache: 'no-store',
      });
      const json = await response.json();
      if (!response.ok || !json.ok) {
        throw new Error(json.message || 'No se pudo cargar la disponibilidad de las cuentas.');
      }
      setData(json);
    } catch (requestError) {
      setError(requestError.message || 'No se pudo cargar la disponibilidad de las cuentas.');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadReport(fecha);
  }, [fecha, loadReport]);

  const cuentas = data?.cuentas || [];
  const bancos = data?.bancos || [];
  const hayPuntoVenta = bancos.some((banco) => banco.tiene_punto_venta);
  const transitorio = data?.pos_por_cobrar || null;

  const handleTransferenciaSuccess = (resultado) => {
    setTransferenciaModalOpen(false);
    showSuccess(resultado.message || 'Transferencia registrada correctamente.');
    loadReport(fecha);
  };

  const handleIngresoSuccess = (resultado) => {
    setIngresoModalOpen(false);
    showSuccess(resultado.message || 'Ingreso registrado correctamente.');
    loadReport(fecha);
  };

  return (
    <section style={containerStyle(isMobile)}>
      <Toast toast={toast} onClose={hideToast} />
      <TransferenciaCuentasModal
        open={transferenciaModalOpen}
        fechaInicial={fecha}
        onClose={() => setTransferenciaModalOpen(false)}
        onSuccess={handleTransferenciaSuccess}
      />
      <IngresoNoFacturadoModal
        open={ingresoModalOpen}
        onClose={() => setIngresoModalOpen(false)}
        onSuccess={handleIngresoSuccess}
      />

      <div className="no-print" style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <button type="button" onClick={onBack} style={backButtonStyle}>
          ← Volver a Contabilidad
        </button>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <ActionMenuSelect
            label="⇄ Transferencias"
            accentColor="var(--vg-f-6d28d9)"
            options={[
              { value: 'nueva', label: '+ Registrar transferencia' },
              { value: 'historial', label: 'Ver historial' },
            ]}
            onSelect={(value) => {
              if (value === 'nueva') setTransferenciaModalOpen(true);
              if (value === 'historial') onViewHistorialTransferencias();
            }}
          />
          <ActionMenuSelect
            label="+ Ingresos parciales"
            accentColor="#0d9488"
            options={[
              { value: 'nuevo', label: '+ Registrar ingreso' },
              { value: 'historial', label: 'Ver historial' },
            ]}
            onSelect={(value) => {
              if (value === 'nuevo') setIngresoModalOpen(true);
              if (value === 'historial') onViewHistorialIngresos();
            }}
          />
          <button type="button" onClick={() => window.print()} style={printButtonStyle}>
            Imprimir / Guardar PDF
          </button>
        </div>
      </div>

      <div style={headerRowStyle(isMobile)}>
        <div>
          <h2 style={titleStyle(isMobile)}>Disponibilidad diaria</h2>
        </div>
        <DiaFecha value={fecha} onChange={setFecha} />
      </div>

      {loading ? <div style={emptyStyle}>Cargando disponibilidad...</div> : null}
      {!loading && error ? <div style={noticeStyle}>{error}</div> : null}

      {!loading && !error && data ? (
        <>
          <section style={panelStyle}>
            <div style={sectionTitleStyle}>Saldo por cuenta — al {fecha}</div>
            {data.tasa_bcv ? (
              <div style={{ fontSize: 12, color: 'var(--vg-f-c8bbbb)' }}>Tasa BCV usada: Bs. {formatMonto(data.tasa_bcv)} / $</div>
            ) : (
              <div style={{ fontSize: 12, color: 'var(--vg-f-ffcf85)' }}>No hay tasa BCV registrada para esta fecha; las cuentas en bolívares no muestran conversión.</div>
            )}

            {hayPuntoVenta ? (
              <div style={{ fontSize: 12, color: 'var(--vg-f-c8bbbb)' }}>
                En los puntos de venta, el saldo disponible solo cuenta los lotes ya acreditados; lo demás está por acreditar.
              </div>
            ) : null}

            <div style={cuentasGridStyle(isMobile)}>
              {bancos.map((banco) => (
                <article key={banco.nombre} style={cuentaCardStyle(Number(banco.saldo_disponible) < 0)}>
                  <div style={cuentaHeaderStyle}>
                    <div style={cuentaNombreStyle}>
                      {banco.nombre}
                      {!banco.agrupado && !banco.metodos[0].activo ? <span style={inactivaBadgeStyle}>Inactiva</span> : null}
                      {banco.moneda_mixta ? <span style={inactivaBadgeStyle}>Monedas mixtas</span> : null}
                      {banco.es_cashea ? <span style={inactivaBadgeStyle}>Por cobrar · no disponible</span> : null}
                    </div>
                  </div>
                  <div style={cuentaSaldoStyle(Number(banco.saldo_disponible) < 0)}>
                    {banco.moneda === 'VES' ? (
                      <>
                        Bs. {banco.saldo_disponible_bs !== null ? formatMonto(banco.saldo_disponible_bs) : '—'}
                        <span style={secondaryAmountStyle}> (${formatMonto(banco.saldo_disponible)})</span>
                      </>
                    ) : (
                      <>${formatMonto(banco.saldo_disponible)}</>
                    )}
                  </div>
                  {banco.tiene_punto_venta ? (
                    <div style={porAcreditarBoxStyle}>
                      <div style={{ fontWeight: 800, color: 'var(--vg-f-ffe3a3)' }}>
                        Por acreditar: {banco.moneda === 'VES' ? `Bs. ${formatMonto(banco.por_acreditar_bs)} ` : ''}
                        <span style={secondaryAmountStyle}>(${formatMonto(banco.por_acreditar_usd)})</span>
                      </div>
                      <div>{banco.lotes_por_acreditar.length} lote(s) sin acreditar</div>
                    </div>
                  ) : null}
                  {/* Las tarjetas muestran solo el saldo: el desglose (cobrado, gastos, proveedores, metodos)
                      confundia. Ese detalle sigue en la tabla "Detalle por cuenta" de mas abajo. */}
                </article>
              ))}
            </div>
          </section>

          {transitorio && Number(transitorio.total_usd) > 0 ? (
            <section style={panelStyle}>
              <div style={sectionTitleStyle}>Puntos de venta por cobrar (transitorio) — al {fecha}</div>
              <div style={{ fontSize: 12.5, color: 'var(--vg-f-c8bbbb)' }}>
                Lotes de punto de venta abiertos o cerrados que todavía no se acreditan: ${formatMonto(transitorio.total_usd)} en total.
              </div>
              <div style={tableWrapStyle}>
                <div style={transitorioTableStyle}>
                  <div style={headStyle}>Banco</div>
                  <div style={headStyle}>Lotes abiertos</div>
                  <div style={headStyle}>Lotes cerrados</div>
                  <div style={headStyle}>Por acreditar</div>
                  {transitorio.por_banco.map((item) => (
                    <Fragment key={item.banco}>
                      <div style={cellStyle}>{item.banco}</div>
                      <div style={cellStyle}>{item.lotes_abiertos}</div>
                      <div style={cellStyle}>{item.lotes_cerrados}</div>
                      <div style={cellStyle}>${formatMonto(item.monto_usd)}</div>
                    </Fragment>
                  ))}
                </div>
              </div>
              {onNavigate ? (
                <button type="button" className="no-print" onClick={() => onNavigate('contabilidad-lotes-pos')} style={verLotesLinkStyle}>
                  Ver lotes de punto de venta →
                </button>
              ) : null}
            </section>
          ) : null}

          <section style={panelStyle}>
            <div style={sectionTitleStyle}>Detalle por cuenta</div>
            <div style={tableWrapStyle}>
              <div style={tableStyle}>
                <div style={headStyle}>Cuenta</div>
                <div style={headStyle}>Cobrado</div>
                <div style={headStyle}>Propinas/extra</div>
                <div style={headStyle}>Gastos</div>
                <div style={headStyle}>Proveedores</div>
                <div style={headStyle}>Consignado</div>
                <div style={headStyle}>Saldo disponible</div>
                <div style={headStyle}>Por acreditar</div>
                {cuentas.map((cuenta) => (
                  <Fragment key={cuenta.id}>
                    <div style={cellStyle}>{cuenta.nombre}{cuenta.es_efectivo ? ' (efectivo)' : ''}</div>
                    <div style={cellStyle}>${formatMonto(cuenta.ingresos_acumulados)}</div>
                    <div style={cellStyle}>${formatMonto(cuenta.ingresos_extra_acumulados)}</div>
                    <div style={cellStyle}>${formatMonto(cuenta.gastos_acumulados)}</div>
                    <div style={cellStyle}>${formatMonto(cuenta.compras_acumuladas)}</div>
                    <div style={cellStyle}>${formatMonto(cuenta.consignado_acumulado)}</div>
                    <div style={{ ...cellStyle, fontWeight: 800, color: Number(cuenta.saldo_disponible) < 0 ? 'var(--vg-f-ff9d9d)' : 'var(--vg-f-8fffb0)' }}>
                      ${formatMonto(cuenta.saldo_disponible)}
                    </div>
                    <div style={cellStyle}>{cuenta.es_punto_venta ? `$${formatMonto(cuenta.por_acreditar_usd)}` : '—'}</div>
                  </Fragment>
                ))}
                <div style={{ ...cellStyle, fontWeight: 800 }}>Total disponible</div>
                <div style={cellStyle} />
                <div style={cellStyle} />
                <div style={cellStyle} />
                <div style={cellStyle} />
                <div style={cellStyle} />
                <div style={{ ...cellStyle, fontWeight: 800 }}>${formatMonto(data.total_disponible)}</div>
                <div style={{ ...cellStyle, fontWeight: 800 }}>${formatMonto(data.total_por_acreditar)}</div>
              </div>
            </div>
          </section>
        </>
      ) : null}
    </section>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const headerRowStyle = (isMobile) => ({ display: 'flex', justifyContent: 'space-between', alignItems: isMobile ? 'flex-start' : 'center', flexDirection: isMobile ? 'column' : 'row', gap: 12 });
const titleStyle = (isMobile) => ({ margin: 0, color: 'var(--vg-text-strong)', fontSize: isMobile ? 28 : 34 });
const subtitleStyle = { margin: '8px 0 0', color: 'var(--vg-f-d2c3c3)', maxWidth: 680, lineHeight: 1.6 };
const panelStyle = { display: 'grid', gap: 14, padding: 18, borderRadius: 20, border: '1px solid rgba(var(--vg-ink), 0.1)', background: 'linear-gradient(180deg, var(--vg-bg-card) 0%, var(--vg-s-080808-a980) 100%)' };
const sectionTitleStyle = { color: 'var(--vg-text-strong)', fontSize: 19, fontWeight: 700 };
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(var(--vg-ink), 0.12)', color: 'var(--vg-f-c8bbbb)' };
const noticeStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid var(--vg-f-ff9191-a220)', background: 'rgba(255,98,98,0.12)', color: 'var(--vg-f-ffd8d8)' };

const cuentasGridStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(auto-fill, minmax(240px, 1fr))', gap: 12 });
const cuentaCardStyle = (negativo) => ({
  display: 'grid', gap: 8, padding: '16px 18px', borderRadius: 16,
  border: negativo ? '1px solid var(--vg-f-ff9191-a300)' : '1px solid rgba(var(--vg-ink), 0.1)',
  background: negativo ? 'rgba(255, 98, 98, 0.08)' : 'rgba(var(--vg-ink), 0.03)',
});
const cuentaHeaderStyle = { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 };
const cuentaNombreStyle = { color: 'var(--vg-text-strong)', fontWeight: 700, fontSize: 15, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' };
const inactivaBadgeStyle = { fontSize: 10.5, fontWeight: 800, color: 'var(--vg-f-c8bbbb)', background: 'rgba(var(--vg-ink), 0.08)', padding: '2px 8px', borderRadius: 999, textTransform: 'uppercase', letterSpacing: '0.04em' };
const cuentaSaldoStyle = (negativo) => ({ fontSize: 22, fontWeight: 800, color: negativo ? 'var(--vg-f-ff9d9d)' : 'var(--vg-text-strong)' });
const secondaryAmountStyle = { color: 'var(--vg-f-c8bbbb)', fontSize: 13, marginLeft: 6, fontWeight: 600 };

const porAcreditarBoxStyle = { display: 'grid', gap: 2, padding: '8px 10px', borderRadius: 10, border: '1px dashed var(--vg-f-ffcf85-a400)', background: 'rgba(255,207,133,0.06)', color: 'var(--vg-f-e8d9b6)', fontSize: 12.5 };
const transitorioTableStyle = { display: 'grid', gridTemplateColumns: 'minmax(140px,1.2fr) repeat(3, minmax(110px,0.8fr))', minWidth: 520, border: '1px solid rgba(var(--vg-ink), 0.08)', borderRadius: 14, overflow: 'hidden' };
const verLotesLinkStyle = { border: 'none', background: 'none', color: 'var(--vg-f-ff9d9d)', fontSize: 13, fontWeight: 700, cursor: 'pointer', padding: 0, textAlign: 'left', width: 'fit-content' };
const tableWrapStyle = { overflowX: 'auto' };
const tableStyle = { display: 'grid', gridTemplateColumns: 'minmax(160px,1.1fr) minmax(110px,0.8fr) minmax(120px,0.8fr) minmax(100px,0.7fr) minmax(120px,0.8fr) minmax(110px,0.7fr) minmax(140px,0.9fr) minmax(120px,0.8fr)', minWidth: 1060, border: '1px solid rgba(var(--vg-ink), 0.08)', borderRadius: 14, overflow: 'hidden' };
const headStyle = { padding: '12px 14px', background: 'rgba(var(--vg-ink), 0.06)', color: 'var(--vg-f-ffb0b0)', fontSize: 12, letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 800 };
const cellStyle = { padding: '14px', borderTop: '1px solid rgba(var(--vg-ink), 0.08)', color: 'var(--vg-f-f2e6e6)', display: 'grid', alignContent: 'center' };

const printButtonStyle = { border: '1px solid rgba(var(--vg-ink), 0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(var(--vg-ink), 0.04)', color: 'var(--vg-text-strong)', fontWeight: 700, cursor: 'pointer' };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };

export default ReporteDisponibilidadCuentasPage;
