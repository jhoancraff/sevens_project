import { useCallback, useEffect, useMemo, useState } from 'react';
import AccionesActaTurno from './AccionesActaTurno';
import ConfirmModal from './ConfirmModal';
import Toast from './Toast';
import useToast from '../hooks/useToast';
import { formatFechaHora, formatMonto } from '../utils/lotesPos';
import {
  TIPO_CIERRE_ESTILO,
  TIPO_CIERRE_ETIQUETA,
  agruparPorMetodo,
  apiCierreTurno,
  claveLinea,
  formatHora,
  hacerCuanto,
  montoPrincipal,
  montoSecundario,
  subtotalGrupo,
} from '../utils/cierreTurno';

// Cerrar turno: quien cobro revisa CADA transaccion que registro (cobros que no son
// de punto de venta + propinas/pagos extra), marca si llego o no, escribe la novedad y
// cierra. Es la misma pantalla para cajera, administrador y contador: tambien sirve
// para cerrar el turno de otra persona que se fue sin cerrar (queda registrado a nombre
// de ambos). Las reglas viven en el backend (cierre_turno.py); aqui solo se ordena la revision.
function CierreTurnoPage({ isMobile, onBack, onNavigate, titularInicialId = null }) {
  const [titularId, setTitularId] = useState(titularInicialId);
  const [estado, setEstado] = useState(null);
  const [datos, setDatos] = useState(null);
  const [marcas, setMarcas] = useState({});
  const [novedad, setNovedad] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [resultado, setResultado] = useState(null);
  const { toast, showSuccess, showError, hideToast } = useToast();

  const cargar = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const consultaTitular = titularId ? `?titular_id=${titularId}` : '';
      const [estadoJson, pendientesJson] = await Promise.all([
        apiCierreTurno('cierre-turno/estado/'),
        apiCierreTurno(`cierre-turno/pendientes/${consultaTitular}`),
      ]);
      setEstado(estadoJson);
      setDatos(pendientesJson);
      // Si se recarga, se conservan las marcas de lo que sigue pendiente.
      setMarcas((previas) => {
        const vigentes = {};
        pendientesJson.lineas.forEach((linea) => {
          const clave = claveLinea(linea);
          if (previas[clave]) vigentes[clave] = previas[clave];
        });
        return vigentes;
      });
    } catch (requestError) {
      setError(requestError.message);
      setDatos(null);
    } finally {
      setLoading(false);
    }
  }, [titularId]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const cambiarTitular = (nuevoId) => {
    setTitularId(nuevoId);
    setMarcas({});
    setNovedad('');
    setResultado(null);
  };

  const marcar = (linea, nuevoEstado) => {
    setMarcas((previas) => ({
      ...previas,
      [claveLinea(linea)]: { estado: nuevoEstado, nota: previas[claveLinea(linea)]?.nota || '' },
    }));
  };

  const escribirNota = (linea, nota) => {
    setMarcas((previas) => ({ ...previas, [claveLinea(linea)]: { ...previas[claveLinea(linea)], nota } }));
  };

  const confirmarGrupo = (grupo) => {
    setMarcas((previas) => {
      const siguientes = { ...previas };
      grupo.lineas.forEach((linea) => {
        const clave = claveLinea(linea);
        if (!siguientes[clave]?.estado) siguientes[clave] = { estado: 'confirmada', nota: '' };
      });
      return siguientes;
    });
  };

  const lineas = datos?.lineas || [];
  const grupos = useMemo(() => agruparPorMetodo(lineas), [lineas]);
  const lotesBloquean = datos?.lotes_pos_abiertos || [];
  const revisadas = lineas.filter((linea) => marcas[claveLinea(linea)]?.estado).length;
  const noLlegaron = lineas.filter((linea) => marcas[claveLinea(linea)]?.estado === 'no_llego');
  const noLlegoSinNota = noLlegaron.filter((linea) => !(marcas[claveLinea(linea)]?.nota || '').trim());
  const requiereNovedad = Boolean(datos?.tipo && datos.tipo !== 'normal') || noLlegaron.length > 0;

  let bloqueo = '';
  if (!datos?.activo) bloqueo = 'El cierre de turno todavía no está activado.';
  else if (lineas.length === 0) bloqueo = 'No hay transacciones pendientes de cierre.';
  else if (lotesBloquean.length > 0) bloqueo = 'Primero hay que cerrar los lotes de punto de venta abiertos.';
  else if (revisadas < lineas.length) bloqueo = `Falta revisar ${lineas.length - revisadas} transacción(es).`;
  else if (noLlegoSinNota.length > 0) bloqueo = 'Explica con una nota por qué no llegó cada transacción marcada.';
  else if (requiereNovedad && !novedad.trim()) bloqueo = 'Escribe la novedad: este cierre la requiere.';

  const cerrarTurno = async () => {
    setSaving(true);
    try {
      const json = await apiCierreTurno('cierre-turno/cerrar/', {
        method: 'POST',
        cuerpo: {
          titular_id: datos.titular.id,
          corte: datos.corte,
          novedad,
          lineas: lineas.map((linea) => ({
            origen: linea.origen,
            id: linea.origen_id,
            estado: marcas[claveLinea(linea)].estado,
            nota: marcas[claveLinea(linea)].nota || '',
          })),
        },
      });
      setConfirmOpen(false);
      setResultado(json.cierre);
      setNovedad('');
      setMarcas({});
      showSuccess(json.message);
      await cargar();
    } catch (requestError) {
      setConfirmOpen(false);
      showError(requestError.message);
      await cargar();
    } finally {
      setSaving(false);
    }
  };

  const ajenos = estado?.pendientes_ajenos || [];
  const cerrandoAjeno = datos && !datos.es_propio;

  return (
    <section style={containerStyle(isMobile)}>
      <Toast toast={toast} onClose={hideToast} />

      <div className="no-print" style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <button type="button" onClick={onBack} style={backButtonStyle}>← Volver</button>
        <button type="button" onClick={cargar} disabled={loading || saving} style={secondaryButtonStyle}>Actualizar</button>
      </div>

      <div>
        <h2 style={titleStyle(isMobile)}>Cerrar turno{cerrandoAjeno ? ` de ${datos.titular.nombre}` : ''}</h2>
        <div style={mutedStyle}>
          Revisa cada transacción contra tu banco o tu caja. Marca las que llegaron y explica las que no.
        </div>
      </div>

      {loading && !datos ? <div style={emptyStyle}>Cargando transacciones...</div> : null}
      {error ? <div style={noticeStyle}>{error}</div> : null}

      {cerrandoAjeno ? (
        <div style={{ ...noticeStyle, borderColor: 'rgba(59,130,246,0.45)', background: 'rgba(59,130,246,0.12)', color: '#d3e8ff' }}>
          Estás cerrando el turno de <strong>{datos.titular.nombre}</strong>. Las transacciones siguen siendo suyas; el
          cierre queda a nombre de los dos y exige novedad.
          {' '}
          <button type="button" onClick={() => cambiarTitular(null)} style={linkButtonStyle}>Volver a mi turno</button>
        </div>
      ) : null}

      {!cerrandoAjeno && ajenos.length > 0 ? (
        <section style={panelStyle}>
          <div style={sectionTitleStyle}>Turnos de otras personas sin cerrar</div>
          <div style={mutedStyle}>Puedes seguir cobrando. Si alguien se fue sin cerrar, puedes cerrar su turno.</div>
          {ajenos.map((fila) => (
            <div key={fila.titular_id} style={filaAjenaStyle}>
              <div>
                <strong>{fila.titular_nombre}</strong>
                <span style={mutedStyle}> · {fila.titular_rol || 'sin rol'} · {fila.cantidad} sin cerrar · {hacerCuanto(fila.mas_antigua)}</span>
              </div>
              <button type="button" onClick={() => cambiarTitular(fila.titular_id)} style={secondaryButtonStyle}>
                Cerrar su turno
              </button>
            </div>
          ))}
        </section>
      ) : null}

      {datos && !datos.activo ? (
        <div style={noticeStyle}>
          El cierre de turno todavía no está activado. Un administrador debe activarlo en «Cierres de turno».
        </div>
      ) : null}

      {lotesBloquean.length > 0 ? (
        <div style={{ ...noticeStyle, borderColor: 'var(--vg-f-ffcf85-a400)', background: 'rgba(255,207,133,0.08)', color: 'var(--vg-f-ffe3a3)' }}>
          Antes de cerrar el turno hay que cerrar {lotesBloquean.length === 1 ? 'el lote' : 'los lotes'} de punto de venta:{' '}
          {lotesBloquean.map((lote) => `#${lote.numero} (${lote.metodo_pago_nombre})`).join(', ')}.
          {' '}
          <button type="button" onClick={() => onNavigate && onNavigate('contabilidad-lotes-pos')} style={linkButtonStyle}>
            Ir a lotes de punto de venta
          </button>
        </div>
      ) : null}

      {resultado ? (
        <section style={{ ...panelStyle, borderColor: 'rgba(70,200,120,0.4)' }}>
          <div style={{ color: 'var(--vg-f-8fffb0)', fontWeight: 800, fontSize: 18 }}>
            Turno cerrado — {resultado.codigo}
          </div>
          <div style={{ color: 'var(--vg-f-f2e6e6)' }}>
            {resultado.total_confirmadas} confirmada(s)
            {resultado.total_no_llegaron > 0 ? ` · ${resultado.total_no_llegaron} que no llegó/llegaron` : ''}
            {' · '}
            <span style={{ ...badgeStyle, ...TIPO_CIERRE_ESTILO[resultado.tipo] }}>{TIPO_CIERRE_ETIQUETA[resultado.tipo]}</span>
          </div>
          <div style={mutedStyle}>
            Cerrado por {resultado.cerrado_por_nombre} el {formatFechaHora(resultado.fecha_cierre)}.
          </div>
          <AccionesActaTurno cierreId={resultado.id} />
          {onNavigate ? (
            <button type="button" onClick={() => onNavigate('contabilidad-cierres-turno')} style={secondaryButtonStyle}>
              Ver mis cierres
            </button>
          ) : null}
        </section>
      ) : null}

      {datos && datos.activo && lineas.length > 0 ? (
        <>
          <section style={panelStyle}>
            <div style={sectionTitleStyle}>Transacciones del turno</div>
            <div style={progresoWrapStyle}>
              <div style={{ ...progresoBarraStyle, width: `${(revisadas / lineas.length) * 100}%` }} />
            </div>
            <div style={mutedStyle}>
              {revisadas} de {lineas.length} revisadas
              {datos.tipo ? (
                <>
                  {' · cierre '}
                  <span style={{ ...badgeStyle, ...TIPO_CIERRE_ESTILO[datos.tipo] }}>{TIPO_CIERRE_ETIQUETA[datos.tipo]}</span>
                  {datos.tipo === 'tardio' ? ` (pasaron más de ${datos.umbral_tardio_horas} h)` : ''}
                </>
              ) : null}
            </div>

            {grupos.map((grupo) => {
              const pendientesGrupo = grupo.lineas.filter((linea) => !marcas[claveLinea(linea)]?.estado);
              return (
                <div key={grupo.clave} style={{ display: 'grid', gap: 8 }}>
                  <div style={grupoHeaderStyle}>
                    <div style={subTitleStyle}>
                      {grupo.nombre} · {grupo.lineas.length} · {subtotalGrupo(grupo.lineas)}
                    </div>
                    {grupo.esEfectivo && pendientesGrupo.length > 0 ? (
                      <button type="button" onClick={() => confirmarGrupo(grupo)} style={secondaryButtonStyle}>
                        Confirmar todos ({pendientesGrupo.length})
                      </button>
                    ) : null}
                  </div>
                  {grupo.lineas.map((linea) => {
                    const marca = marcas[claveLinea(linea)] || {};
                    return (
                      <article key={claveLinea(linea)} style={lineaCardStyle(marca.estado)}>
                        <div style={lineaTopStyle}>
                          <div style={{ display: 'grid', gap: 2, minWidth: 0 }}>
                            <div style={{ fontWeight: 700, color: 'var(--vg-text-strong)' }}>
                              {montoPrincipal(linea)}
                              {montoSecundario(linea) ? <span style={mutedStyle}> · {montoSecundario(linea)}</span> : null}
                            </div>
                            <div style={lineaDetalleStyle}>
                              {formatHora(linea.fecha_transaccion)} · {linea.concepto}
                              {linea.cliente ? ` · ${linea.cliente}` : ''}
                            </div>
                            <div style={lineaDetalleStyle}>
                              {linea.referencia && !String(linea.referencia).startsWith('ABONO-') ? `Ref: ${linea.referencia}` : 'Sin referencia'}
                              {linea.numero_cobro ? ` · COB-${String(linea.numero_cobro).padStart(6, '0')}` : ''}
                              {linea.saldo_posterior !== null && linea.saldo_posterior !== undefined && Number(linea.saldo_posterior) > 0
                                ? ` · saldo restante $${formatMonto(linea.saldo_posterior)}`
                                : ''}
                            </div>
                          </div>
                          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                            <button
                              type="button"
                              onClick={() => marcar(linea, 'confirmada')}
                              style={chipStyle(marca.estado === 'confirmada', 'ok')}
                            >
                              ✓ Llegó
                            </button>
                            <button
                              type="button"
                              onClick={() => marcar(linea, 'no_llego')}
                              style={chipStyle(marca.estado === 'no_llego', 'mal')}
                            >
                              ✗ No llegó
                            </button>
                          </div>
                        </div>
                        {marca.estado === 'no_llego' ? (
                          <input
                            type="text"
                            value={marca.nota || ''}
                            onChange={(event) => escribirNota(linea, event.target.value)}
                            placeholder="¿Qué pasó? (obligatorio)"
                            style={inputStyle}
                          />
                        ) : null}
                      </article>
                    );
                  })}
                </div>
              );
            })}
          </section>

          <section style={panelStyle}>
            <div style={sectionTitleStyle}>Novedad</div>
            <textarea
              value={novedad}
              onChange={(event) => setNovedad(event.target.value)}
              rows={3}
              placeholder={requiereNovedad ? 'Obligatoria para este cierre' : 'Sin novedad (opcional)'}
              style={{ ...inputStyle, resize: 'vertical' }}
            />
            {bloqueo ? <div style={mutedStyle}>{bloqueo}</div> : null}
            <button
              type="button"
              disabled={Boolean(bloqueo) || saving}
              onClick={() => setConfirmOpen(true)}
              style={{ ...dangerButtonStyle, opacity: bloqueo ? 0.5 : 1, cursor: bloqueo ? 'not-allowed' : 'pointer' }}
            >
              Cerrar turno
            </button>
          </section>
        </>
      ) : null}

      {datos && datos.activo && lineas.length === 0 && !loading ? (
        <div style={emptyStyle}>
          {cerrandoAjeno
            ? `${datos.titular.nombre} no tiene transacciones pendientes de cierre.`
            : 'No tienes transacciones pendientes de cierre.'}
        </div>
      ) : null}

      <ConfirmModal
        open={confirmOpen}
        busy={saving}
        title="¿Cerrar el turno?"
        confirmLabel="Cerrar turno"
        onCancel={() => setConfirmOpen(false)}
        onConfirm={cerrarTurno}
        message={(
          <div style={{ display: 'grid', gap: 6 }}>
            <div>{lineas.length - noLlegaron.length} transacción(es) confirmada(s).</div>
            {noLlegaron.length > 0 ? (
              <div style={{ color: 'var(--vg-f-ff9d9d)', fontWeight: 700 }}>
                {noLlegaron.length} marcada(s) como «no llegó».
              </div>
            ) : null}
            {cerrandoAjeno ? <div>Es el turno de {datos.titular.nombre}: quedará a nombre de ambos.</div> : null}
            <div>El acta queda registrada de forma permanente.</div>
          </div>
        )}
      />
    </section>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const titleStyle = (isMobile) => ({ margin: 0, color: 'var(--vg-text-strong)', fontSize: isMobile ? 26 : 34 });
const panelStyle = { display: 'grid', gap: 14, padding: 18, borderRadius: 20, border: '1px solid rgba(var(--vg-ink), 0.1)', background: 'linear-gradient(180deg, var(--vg-bg-card) 0%, var(--vg-s-080808-a980) 100%)' };
const sectionTitleStyle = { color: 'var(--vg-text-strong)', fontSize: 19, fontWeight: 700 };
const subTitleStyle = { color: 'var(--vg-f-ffb0b0)', fontSize: 12, fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase' };
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(var(--vg-ink), 0.12)', color: 'var(--vg-f-c8bbbb)', padding: 12, textAlign: 'center' };
const noticeStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid var(--vg-f-ff9191-a220)', background: 'rgba(255,98,98,0.12)', color: 'var(--vg-f-ffd8d8)' };
const mutedStyle = { color: 'var(--vg-f-a89999)', fontSize: 12.5 };
const filaAjenaStyle = { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap', padding: '10px 12px', borderRadius: 12, border: '1px solid rgba(var(--vg-ink), 0.1)', background: 'rgba(var(--vg-ink), 0.03)', color: 'var(--vg-f-f2e6e6)' };
const progresoWrapStyle = { height: 8, borderRadius: 999, background: 'rgba(var(--vg-ink), 0.1)', overflow: 'hidden' };
const progresoBarraStyle = { height: '100%', borderRadius: 999, background: 'linear-gradient(90deg, #22c55e, #86efac)', transition: 'width 160ms ease' };
const grupoHeaderStyle = { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginTop: 6 };
const lineaCardStyle = (estado) => ({
  display: 'grid',
  gap: 8,
  padding: '12px 14px',
  borderRadius: 14,
  border: `1px solid ${estado === 'confirmada' ? 'rgba(70,200,120,0.45)' : estado === 'no_llego' ? 'rgba(255,98,98,0.55)' : 'rgba(var(--vg-ink), 0.1)'}`,
  background: estado === 'confirmada' ? 'rgba(70,200,120,0.07)' : estado === 'no_llego' ? 'rgba(255,98,98,0.08)' : 'rgba(var(--vg-ink), 0.03)',
});
const lineaTopStyle = { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' };
const lineaDetalleStyle = { color: 'var(--vg-f-d2c3c3)', fontSize: 12.5, overflowWrap: 'anywhere' };
const chipStyle = (activo, tipo) => ({
  border: `1px solid ${activo ? (tipo === 'ok' ? 'rgba(70,200,120,0.7)' : 'rgba(255,98,98,0.75)') : 'rgba(var(--vg-ink), 0.18)'}`,
  borderRadius: 999,
  padding: '9px 16px',
  background: activo ? (tipo === 'ok' ? 'rgba(70,200,120,0.25)' : 'rgba(255,98,98,0.25)') : 'rgba(var(--vg-ink), 0.05)',
  color: 'var(--vg-text-strong)',
  fontWeight: 700,
  cursor: 'pointer',
  minHeight: 40,
});
const badgeStyle = { fontSize: 11, fontWeight: 800, padding: '3px 10px', borderRadius: 999, textTransform: 'uppercase', letterSpacing: '0.04em' };
const inputStyle = { borderRadius: 12, border: '1px solid rgba(var(--vg-ink), 0.14)', background: 'var(--vg-s-161010)', padding: '10px 12px', color: 'var(--vg-text-strong)', width: '100%', boxSizing: 'border-box', font: 'inherit' };
const secondaryButtonStyle = { border: '1px solid rgba(var(--vg-ink), 0.18)', borderRadius: 999, padding: '9px 16px', background: 'rgba(var(--vg-ink), 0.05)', color: 'var(--vg-text-strong)', fontWeight: 700, cursor: 'pointer', width: 'fit-content' };
const linkButtonStyle = { border: 'none', background: 'none', color: 'inherit', textDecoration: 'underline', fontWeight: 700, cursor: 'pointer', padding: 0 };
const dangerButtonStyle = { border: '1px solid var(--vg-f-ff7e7e-a400)', borderRadius: 999, padding: '12px 16px', background: 'rgba(145,33,33,0.35)', color: 'var(--vg-f-ffd3d3)', fontWeight: 700 };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };

export default CierreTurnoPage;
