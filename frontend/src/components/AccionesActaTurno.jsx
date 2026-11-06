import { useState } from 'react';
import BotonDescargarPdf from './BotonDescargarPdf';
import { apiCierreTurno } from '../utils/cierreTurno';

// Reimprimir el ticket del acta de un cierre de turno en la impresora de caja, o bajar
// el acta A4 en PDF. El mensaje del resultado queda debajo de los botones (una falla de
// impresora no tumba nada: el turno ya esta cerrado).
function AccionesActaTurno({ cierreId }) {
  const [imprimiendo, setImprimiendo] = useState(false);
  const [mensaje, setMensaje] = useState(null);

  const imprimir = async () => {
    setImprimiendo(true);
    setMensaje(null);
    try {
      const json = await apiCierreTurno('cierre-turno/imprimir/', { method: 'POST', cuerpo: { cierre_id: cierreId } });
      setMensaje({ ok: true, texto: json.message || 'Acta enviada a la impresora.' });
    } catch (error) {
      setMensaje({ ok: false, texto: error.message || 'No se pudo imprimir el acta.' });
    } finally {
      setImprimiendo(false);
    }
  };

  return (
    <div className="no-print" style={{ display: 'grid', gap: 6 }}>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button type="button" onClick={imprimir} disabled={imprimiendo} style={botonStyle}>
          {imprimiendo ? 'Imprimiendo...' : 'Imprimir ticket'}
        </button>
        <BotonDescargarPdf
          url="/api/cierre-turno/acta-pdf/"
          params={{ cierre_id: cierreId }}
          onError={(texto) => setMensaje({ ok: false, texto })}
          style={botonStyle}
        >
          Descargar PDF
        </BotonDescargarPdf>
      </div>
      {mensaje ? (
        <div role="status" style={{ fontSize: 12.5, color: mensaje.ok ? 'var(--vg-f-8fffb0)' : 'var(--vg-f-ffd8d8)' }}>
          {mensaje.texto}
        </div>
      ) : null}
    </div>
  );
}

const botonStyle = {
  border: '1px solid rgba(var(--vg-ink), 0.18)',
  borderRadius: 999,
  padding: '9px 16px',
  background: 'rgba(var(--vg-ink), 0.05)',
  color: 'var(--vg-text-strong)',
  fontWeight: 700,
  cursor: 'pointer',
};

export default AccionesActaTurno;
