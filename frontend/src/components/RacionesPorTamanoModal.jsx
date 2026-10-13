function RacionesPorTamanoModal({ open, productos, filas, onAddFila, onRemoveFila, onUpdateFila, onClose }) {
  if (!open) {
    return null;
  }

  return (
    <div style={backdropStyle} onClick={onClose}>
      <div style={cardStyle} onClick={(event) => event.stopPropagation()}>
        <div style={titleStyle}>Tabla de raciones por tamaño</div>

        {productos.length === 0 ? (
          <p style={emptyStyle}>Esta categoría todavía no tiene productos.</p>
        ) : (
          <div style={rowsWrapStyle}>
            {filas.map((fila) => (
              <div key={fila.uid} style={rowStyle}>
                <input
                  type="number"
                  min="1"
                  step="1"
                  placeholder="Gramos"
                  value={fila.tramo_peso}
                  onChange={(event) => onUpdateFila(fila.uid, 'tramo_peso', event.target.value)}
                  style={inputStyle}
                />
                <select
                  value={fila.producto_id}
                  onChange={(event) => onUpdateFila(fila.uid, 'producto_id', event.target.value)}
                  style={inputStyle}
                >
                  <option value="">Selecciona un producto...</option>
                  {productos.map((producto) => (
                    <option key={producto.id} value={producto.id}>{producto.nombre}</option>
                  ))}
                </select>
                <input
                  type="number"
                  min="0.01"
                  step="0.01"
                  placeholder="Cantidad"
                  value={fila.cantidad}
                  onChange={(event) => onUpdateFila(fila.uid, 'cantidad', event.target.value)}
                  style={inputStyle}
                />
                <button type="button" onClick={() => onRemoveFila(fila.uid)} style={removeButtonStyle}>
                  Quitar
                </button>
              </div>
            ))}
          </div>
        )}

        <div style={footerStyle}>
          <button type="button" onClick={onAddFila} disabled={productos.length === 0} style={addButtonStyle}>
            Agregar fila
          </button>
          <button type="button" onClick={onClose} style={closeButtonStyle}>
            Cerrar
          </button>
        </div>
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
  maxHeight: '85vh',
  overflowY: 'auto',
  borderRadius: 20,
  border: '1px solid var(--vg-f-ff9191-a300)',
  background: 'linear-gradient(180deg, var(--vg-s-1c0c0c-a980) 0%, var(--vg-s-0a0808-a990) 100%)',
  padding: '22px 22px 18px',
  boxShadow: '0 20px 50px rgba(0, 0, 0, calc(0.45 * var(--vg-shadow-k)))',
};

const titleStyle = {
  color: 'var(--vg-text-strong)',
  fontSize: 19,
  fontWeight: 800,
  marginBottom: 14,
};

const emptyStyle = {
  margin: 0,
  color: 'var(--vg-f-d2c3c3)',
  fontSize: 14,
};

const rowsWrapStyle = {
  display: 'grid',
  gap: 10,
};

const rowStyle = {
  display: 'grid',
  gridTemplateColumns: 'minmax(80px, 0.7fr) minmax(140px, 1.6fr) minmax(90px, 0.8fr) auto',
  gap: 8,
  alignItems: 'center',
};

const inputStyle = {
  width: '100%',
  padding: '10px 12px',
  borderRadius: 12,
  border: '1px solid rgba(var(--vg-ink), 0.16)',
  background: 'rgba(var(--vg-ink), 0.05)',
  color: 'var(--vg-text-strong)',
  fontSize: 14,
};

const removeButtonStyle = {
  border: '1px solid var(--vg-f-ff7e7e-a400)',
  borderRadius: 999,
  padding: '9px 14px',
  background: 'rgba(145, 33, 33, 0.35)',
  color: 'var(--vg-f-ffd3d3)',
  fontWeight: 700,
  cursor: 'pointer',
  whiteSpace: 'nowrap',
};

const footerStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  gap: 10,
  marginTop: 20,
  flexWrap: 'wrap',
};

const addButtonStyle = {
  border: '1px solid rgba(var(--vg-ink), 0.16)',
  borderRadius: 999,
  padding: '10px 16px',
  background: 'rgba(var(--vg-ink), 0.05)',
  color: 'var(--vg-text-strong)',
  fontWeight: 700,
  cursor: 'pointer',
};

const closeButtonStyle = {
  border: '1px solid var(--vg-f-ff5a5a-a500)',
  borderRadius: 999,
  padding: '10px 16px',
  background: 'rgba(255, 60, 60, 0.18)',
  color: 'var(--vg-f-ffb3b3)',
  fontWeight: 700,
  cursor: 'pointer',
};

export default RacionesPorTamanoModal;
