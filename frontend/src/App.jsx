import { useState, useEffect } from 'react'
import './App.css'

function App() {
  const [backendStatus, setBackendStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'

  const checkBackend = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${apiUrl}/status/`)
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`)
      }
      const data = await res.json()
      setBackendStatus(data)
    } catch (err) {
      setError(err.message)
      setBackendStatus(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    checkBackend()
  }, [])

  return (
    <div style={{ maxWidth: '800px', margin: '0 auto', padding: '2rem', fontFamily: 'system-ui, sans-serif' }}>
      <header style={{ textAlign: 'center', marginBottom: '2rem' }}>
        <h1 style={{ fontSize: '2.5rem', marginBottom: '0.5rem', color: '#1a365d' }}>Entorno Sevens Configurado</h1>
        <p style={{ color: '#4a5568' }}>PostgreSQL 18 + Django 6 + Gunicorn + React + Git</p>
      </header>

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
        gap: '1.25rem',
        marginBottom: '2rem'
      }}>
        <div style={{ border: '1px solid #e2e8f0', borderRadius: '10px', padding: '1.25rem', background: '#f8fafc' }}>
          <h3 style={{ margin: '0 0 0.5rem 0', color: '#2b6cb0' }}>🐘 PostgreSQL</h3>
          <p style={{ margin: '0.25rem 0' }}><strong>BD:</strong> sevensdb</p>
          <p style={{ margin: '0.25rem 0' }}><strong>Usuario:</strong> sevens</p>
          <p style={{ margin: '0.25rem 0' }}><strong>Host:</strong> localhost:5432</p>
          <span style={{
            display: 'inline-block',
            padding: '0.25rem 0.6rem',
            borderRadius: '999px',
            fontSize: '0.8rem',
            fontWeight: 'bold',
            background: '#c6f6d5',
            color: '#22543d',
            marginTop: '0.5rem'
          }}>Activo y Configurado</span>
        </div>

        <div style={{ border: '1px solid #e2e8f0', borderRadius: '10px', padding: '1.25rem', background: '#f8fafc' }}>
          <h3 style={{ margin: '0 0 0.5rem 0', color: '#2b6cb0' }}>🦄 Django + Gunicorn</h3>
          <p style={{ margin: '0.25rem 0' }}><strong>Backend:</strong> Django 6.1</p>
          <p style={{ margin: '0.25rem 0' }}><strong>WSGI:</strong> Gunicorn</p>
          <p style={{ margin: '0.25rem 0' }}><strong>Puerto:</strong> 8000</p>
          <span style={{
            display: 'inline-block',
            padding: '0.25rem 0.6rem',
            borderRadius: '999px',
            fontSize: '0.8rem',
            fontWeight: 'bold',
            background: '#c6f6d5',
            color: '#22543d',
            marginTop: '0.5rem'
          }}>Configurado con .env</span>
        </div>

        <div style={{ border: '1px solid #e2e8f0', borderRadius: '10px', padding: '1.25rem', background: '#f8fafc' }}>
          <h3 style={{ margin: '0 0 0.5rem 0', color: '#2b6cb0' }}>⚛️ React + Vite</h3>
          <p style={{ margin: '0.25rem 0' }}><strong>Frontend:</strong> React 19</p>
          <p style={{ margin: '0.25rem 0' }}><strong>Tooling:</strong> Vite 6</p>
          <p style={{ margin: '0.25rem 0' }}><strong>Env:</strong> .env protegido</p>
          <span style={{
            display: 'inline-block',
            padding: '0.25rem 0.6rem',
            borderRadius: '999px',
            fontSize: '0.8rem',
            fontWeight: 'bold',
            background: '#c6f6d5',
            color: '#22543d',
            marginTop: '0.5rem'
          }}>Listo</span>
        </div>
      </div>

      <div style={{
        border: '1px solid #cbd5e1',
        borderRadius: '10px',
        padding: '1.5rem',
        background: '#ffffff',
        marginBottom: '2rem'
      }}>
        <h3 style={{ marginTop: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span>Prueba de Comunicación Frontend ↔ Backend</span>
          <button
            onClick={checkBackend}
            style={{
              padding: '0.4rem 0.8rem',
              backgroundColor: '#3182ce',
              color: 'white',
              border: 'none',
              borderRadius: '6px',
              cursor: 'pointer'
            }}
          >
            Reintentar
          </button>
        </h3>

        {loading && <p style={{ color: '#718096' }}>Consultando API en {apiUrl}/status/ ...</p>}
        {error && (
          <div style={{ padding: '0.75rem', background: '#fff5f5', color: '#c53030', borderRadius: '6px' }}>
            <p style={{ margin: 0 }}><strong>No se pudo conectar al Backend:</strong> {error}</p>
            <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.85rem' }}>
              Asegúrate de que Gunicorn o Django esté corriendo en <code>http://localhost:8000</code>.
            </p>
          </div>
        )}
        {backendStatus && (
          <div style={{ padding: '0.75rem', background: '#f0fff4', color: '#276749', borderRadius: '6px' }}>
            <p style={{ margin: 0 }}><strong>Conexión exitosa con el Backend:</strong></p>
            <pre style={{ margin: '0.5rem 0 0 0', background: '#2d3748', color: '#edf2f7', padding: '0.75rem', borderRadius: '6px', overflowX: 'auto' }}>
              {JSON.stringify(backendStatus, null, 2)}
            </pre>
          </div>
        )}
      </div>

      <footer style={{
        padding: '1rem',
        background: '#f7fafc',
        borderRadius: '8px',
        fontSize: '0.9rem',
        color: '#4a5568'
      }}>
        <p style={{ margin: 0 }}>
          🔒 <strong>Seguridad Git:</strong> Todas las credenciales están aisladas en archivos <code>.env</code> y completamente excluidas por <code>.gitignore</code>.
        </p>
      </footer>
    </div>
  )
}

export default App
