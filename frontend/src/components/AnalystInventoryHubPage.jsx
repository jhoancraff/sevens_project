// Las opciones van agrupadas: lo que es de ingredientes, lo de utensilios y equipos, y la vista que
// junta los dos.
const grupos = [
  {
    id: 'ingredientes',
    titulo: 'Ingredientes',
    opciones: [
      { id: 'create', title: 'Crear ingredientes', detalle: 'Uno por uno, por lote o desde Excel' },
      { id: 'view', title: 'Ver inventario actual', detalle: 'Stock, costos, filtro por categoría y PDF' },
      { id: 'adjust', title: 'Ajuste de inventario', detalle: 'Corregir el stock tras un conteo' },
      { id: 'categories', title: 'Categorías de inventario', detalle: 'Condimentos, carnes, granos, bolsas...' },
    ],
  },
  {
    id: 'utensilios',
    titulo: 'Utensilios y equipos',
    opciones: [
      { id: 'activos', title: 'Utensilios y equipos', detalle: 'Neveras, platos, impresoras, franelas...' },
      { id: 'activos-categories', title: 'Categorías de utensilios', detalle: 'Vajilla, electrodomésticos, uniformes...' },
    ],
  },
  {
    id: 'general',
    titulo: 'Vista general',
    opciones: [
      { id: 'general', title: 'Todo el inventario', detalle: 'Ingredientes y utensilios, juntos o separados' },
      { id: 'movimientos', title: 'Movimientos del inventario', detalle: 'Qué entró, salió o se ajustó, y por qué hay ese stock' },
    ],
  },
];

function AnalystInventoryHubPage({
  isMobile, onBack, onCreate, onViewInventory, onAdjustInventory, onCategories,
  onActivos, onActivosCategories, onGeneral, onMovimientos,
}) {
  const handlers = {
    create: onCreate, view: onViewInventory, adjust: onAdjustInventory, categories: onCategories,
    activos: onActivos, 'activos-categories': onActivosCategories, general: onGeneral, movimientos: onMovimientos,
  };

  return (
    <section style={containerStyle(isMobile)}>
      <button type="button" onClick={onBack} style={backButtonStyle}>
        ← Volver a Contabilidad
      </button>

      <div>
        <h2 style={titleStyle(isMobile)}>Inventario</h2>
      </div>

      {grupos.map((grupo) => (
        <div key={grupo.id} style={grupoStyle}>
          <div style={grupoTituloStyle}>{grupo.titulo}</div>
          <div style={gridStyle(isMobile)}>
            {grupo.opciones.map((option) => (
              <button
                key={option.id}
                type="button"
                onClick={handlers[option.id]}
                style={cardButtonStyle}
              >
                <div style={cardTitleStyle}>{option.title}</div>
                <span style={cardDescriptionStyle}>{option.detalle}</span>
              </button>
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };
const titleStyle = (isMobile) => ({ margin: 0, color: 'var(--vg-text-strong)', fontSize: isMobile ? 28 : 34 });
const subtitleStyle = { margin: '8px 0 0', color: 'var(--vg-f-d2c3c3)', lineHeight: 1.6, maxWidth: 760 };

const gridStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(2, minmax(0, 1fr))', gap: 16 });
const cardButtonStyle = {
  display: 'grid', gap: 6, textAlign: 'left', padding: '18px 20px', borderRadius: 20,
  border: '1px solid rgba(var(--vg-ink), 0.1)',
  background: 'linear-gradient(180deg, var(--vg-bg-card) 0%, var(--vg-s-080808-a980) 100%)',
  color: 'var(--vg-text-strong)', cursor: 'pointer', boxShadow: '0 12px 30px rgba(0, 0, 0, calc(0.24 * var(--vg-shadow-k)))',
};
const cardTitleStyle = { fontSize: 18, fontWeight: 700 };
const cardDescriptionStyle = { color: 'var(--vg-f-d0c4c4)', lineHeight: 1.6, fontSize: 14 };
const cardLinkStyle = { color: 'var(--vg-f-ff8f8f)', fontWeight: 700, letterSpacing: '0.04em' };

const grupoStyle = { display: 'grid', gap: 10 };
const grupoTituloStyle = { color: 'var(--vg-f-ffb0b0)', fontSize: 12, fontWeight: 800, letterSpacing: '0.1em', textTransform: 'uppercase' };

export default AnalystInventoryHubPage;
