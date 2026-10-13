function BrandHeader({ subtitle = 'Control de cocina y servicio' }) {
  return (
    <div style={{ textAlign: 'center', marginBottom: 24 }}>
      <div style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: 72,
        height: 72,
        borderRadius: 24,
        background: '#fff',
        boxShadow: '0 8px 20px rgba(0, 0, 0, calc(0.25 * var(--vg-shadow-k)))',
        marginBottom: 12,
        overflow: 'hidden',
      }}>
        <img src="/assets/sevens-logo.png" alt="Seven logo" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
      </div>
      <div style={{ fontSize: 34, fontWeight: 700, color: 'var(--vg-accent-primary)' }}>Seven</div>
      <div style={{ color: 'var(--vg-text-secondary)', marginTop: 8, fontSize: 15 }}>{subtitle}</div>
    </div>
  );
}

export default BrandHeader;
