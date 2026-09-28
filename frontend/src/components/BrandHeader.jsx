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
        boxShadow: '0 8px 20px rgba(0, 0, 0, 0.25)',
        marginBottom: 12,
        overflow: 'hidden',
      }}>
        <img src="/assets/sevens-logo.png" alt="Seven logo" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
      </div>
      <div style={{ fontSize: 34, fontWeight: 700, color: '#ff4d4d' }}>Seven</div>
      <div style={{ color: '#c8c8c8', marginTop: 8, fontSize: 15 }}>{subtitle}</div>
    </div>
  );
}

export default BrandHeader;
