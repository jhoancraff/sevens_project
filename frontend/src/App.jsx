import { useState, useEffect } from 'react'
import './App.css'

function App() {
  const [backendStatus, setBackendStatus] = useState(null)
  const [items, setItems] = useState([])
  const [newTitle, setNewTitle] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [loading, setLoading] = useState(true)
  const [itemsLoading, setItemsLoading] = useState(false)
  const [error, setError] = useState(null)

  const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'

  const fetchStatus = async () => {
    try {
      const res = await fetch(`${apiUrl}/status/`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setBackendStatus(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const fetchItems = async () => {
    setItemsLoading(true)
    try {
      const res = await fetch(`${apiUrl}/items/`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setItems(data)
    } catch (err) {
      console.error('Error fetching items:', err)
    } finally {
      setItemsLoading(false)
    }
  }

  useEffect(() => {
    fetchStatus()
    fetchItems()
  }, [])

  const handleAddItem = async (e) => {
    e.preventDefault()
    if (!newTitle.trim()) return

    try {
      const res = await fetch(`${apiUrl}/items/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: newTitle.trim(),
          description: newDesc.trim(),
          completed: false
        })
      })
      if (!res.ok) throw new Error('Error al guardar en PostgreSQL')
      const created = await res.json()
      setItems([created, ...items])
      setNewTitle('')
      setNewDesc('')
    } catch (err) {
      alert(err.message)
    }
  }

  const handleToggle = async (item) => {
    try {
      const res = await fetch(`${apiUrl}/items/${item.id}/`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ completed: !item.completed })
      })
      if (!res.ok) throw new Error('Error al actualizar')
      const updated = await res.json()
      setItems(items.map((i) => (i.id === item.id ? updated : i)))
    } catch (err) {
      alert(err.message)
    }
  }

  const handleDelete = async (id) => {
    try {
      const res = await fetch(`${apiUrl}/items/${id}/`, {
        method: 'DELETE'
      })
      if (!res.ok) throw new Error('Error al eliminar')
      setItems(items.filter((i) => i.id !== id))
    } catch (err) {
      alert(err.message)
    }
  }

  return (
    <div style={{ maxWidth: '880px', margin: '0 auto', padding: '2rem 1.5rem', fontFamily: 'system-ui, -apple-system, sans-serif' }}>
      <header style={{ textAlign: 'center', marginBottom: '2rem' }}>
        <h1 style={{ fontSize: '2.4rem', margin: '0 0 0.5rem 0', color: '#0f172a' }}>
          Stack Fullstack: PostgreSQL + Django + React
        </h1>
        <p style={{ color: '#475569', fontSize: '1.05rem', margin: 0 }}>
          Servido mediante Gunicorn y gestionado con Git de forma segura
        </p>
      </header>

      {/* Grid de Servicios */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
        gap: '1rem',
        marginBottom: '2rem'
      }}>
        <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '12px', padding: '1.2rem' }}>
          <h3 style={{ margin: '0 0 0.5rem 0', color: '#1e40af', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span>🐘</span> PostgreSQL 18
          </h3>
          <p style={{ margin: '0.2rem 0', fontSize: '0.9rem', color: '#334155' }}>
            <strong>Base:</strong> sevensdb
          </p>
          <p style={{ margin: '0.2rem 0', fontSize: '0.9rem', color: '#334155' }}>
            <strong>Usuario:</strong> sevens
          </p>
          <span style={{
            display: 'inline-block',
            marginTop: '0.5rem',
            background: '#dcfce7',
            color: '#166534',
            padding: '0.2rem 0.6rem',
            borderRadius: '999px',
            fontSize: '0.75rem',
            fontWeight: '600'
          }}>
            {backendStatus?.database?.status === 'connected' ? '● Conectado a BD' : 'Conectando...'}
          </span>
        </div>

        <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '12px', padding: '1.2rem' }}>
          <h3 style={{ margin: '0 0 0.5rem 0', color: '#1e40af', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span>🦄</span> Django 6 + Gunicorn
          </h3>
          <p style={{ margin: '0.2rem 0', fontSize: '0.9rem', color: '#334155' }}>
            <strong>Servicio:</strong> systemd (puerto 8000)
          </p>
          <p style={{ margin: '0.2rem 0', fontSize: '0.9rem', color: '#334155' }}>
            <strong>API:</strong> Django REST Framework
          </p>
          <span style={{
            display: 'inline-block',
            marginTop: '0.5rem',
            background: backendStatus ? '#dcfce7' : '#fee2e2',
            color: backendStatus ? '#166534' : '#991b1b',
            padding: '0.2rem 0.6rem',
            borderRadius: '999px',
            fontSize: '0.75rem',
            fontWeight: '600'
          }}>
            {backendStatus ? '● Servicio Activo' : 'Inactivo'}
          </span>
        </div>

        <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '12px', padding: '1.2rem' }}>
          <h3 style={{ margin: '0 0 0.5rem 0', color: '#1e40af', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span>⚛️</span> React + Vite
          </h3>
          <p style={{ margin: '0.2rem 0', fontSize: '0.9rem', color: '#334155' }}>
            <strong>Framework:</strong> React 19
          </p>
          <p style={{ margin: '0.2rem 0', fontSize: '0.9rem', color: '#334155' }}>
            <strong>Seguridad:</strong> .env en .gitignore
          </p>
          <span style={{
            display: 'inline-block',
            marginTop: '0.5rem',
            background: '#dcfce7',
            color: '#166534',
            padding: '0.2rem 0.6rem',
            borderRadius: '999px',
            fontSize: '0.75rem',
            fontWeight: '600'
          }}>
            ● Producción Ready
          </span>
        </div>
      </div>

      {/* Sección CRUD Items en PostgreSQL */}
      <section style={{
        background: '#ffffff',
        border: '1px solid #cbd5e1',
        borderRadius: '12px',
        padding: '1.5rem',
        boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
        marginBottom: '2rem'
      }}>
        <h2 style={{ fontSize: '1.35rem', margin: '0 0 1rem 0', color: '#0f172a' }}>
          Registros en Base de Datos (CRUD en Vivo)
        </h2>

        {/* Formulario para agregar */}
        <form onSubmit={handleAddItem} style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginBottom: '1.5rem' }}>
          <input
            type="text"
            placeholder="Título del elemento..."
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            style={{
              padding: '0.75rem',
              borderRadius: '8px',
              border: '1px solid #cbd5e1',
              fontSize: '0.95rem'
            }}
            required
          />
          <input
            type="text"
            placeholder="Descripción u observaciones..."
            value={newDesc}
            onChange={(e) => setNewDesc(e.target.value)}
            style={{
              padding: '0.75rem',
              borderRadius: '8px',
              border: '1px solid #cbd5e1',
              fontSize: '0.95rem'
            }}
          />
          <button
            type="submit"
            style={{
              alignSelf: 'flex-start',
              padding: '0.65rem 1.25rem',
              background: '#2563eb',
              color: 'white',
              border: 'none',
              borderRadius: '8px',
              fontWeight: '600',
              cursor: 'pointer'
            }}
          >
            + Guardar en PostgreSQL
          </button>
        </form>

        {/* Lista de registros */}
        {itemsLoading && <p style={{ color: '#64748b' }}>Cargando registros de PostgreSQL...</p>}
        {!itemsLoading && items.length === 0 && (
          <p style={{ color: '#64748b', fontStyle: 'italic' }}>No hay registros guardados en sevensdb aún.</p>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          {items.map((item) => (
            <div
              key={item.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '0.75rem 1rem',
                border: '1px solid #e2e8f0',
                borderRadius: '8px',
                background: item.completed ? '#f8fafc' : '#ffffff'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <input
                  type="checkbox"
                  checked={item.completed}
                  onChange={() => handleToggle(item)}
                  style={{ width: '18px', height: '18px', cursor: 'pointer' }}
                />
                <div>
                  <h4 style={{
                    margin: 0,
                    fontSize: '1rem',
                    textDecoration: item.completed ? 'line-through' : 'none',
                    color: item.completed ? '#94a3b8' : '#1e293b'
                  }}>
                    {item.title}
                  </h4>
                  {item.description && (
                    <p style={{ margin: '0.2rem 0 0 0', fontSize: '0.85rem', color: '#64748b' }}>
                      {item.description}
                    </p>
                  )}
                </div>
              </div>
              <button
                onClick={() => handleDelete(item.id)}
                style={{
                  background: '#ef4444',
                  color: 'white',
                  border: 'none',
                  padding: '0.35rem 0.75rem',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  fontSize: '0.8rem'
                }}
              >
                Eliminar
              </button>
            </div>
          ))}
        </div>
      </section>

      {/* Resumen de Seguridad */}
      <footer style={{
        padding: '1rem 1.25rem',
        background: '#f1f5f9',
        borderRadius: '10px',
        color: '#334155',
        fontSize: '0.85rem',
        lineHeight: '1.5'
      }}>
        🛡️ <strong>Seguridad Git:</strong> Las contraseñas, URLs de bases de datos y tokens se leen únicamente de variables de entorno en <code>backend/.env</code>. El archivo <code>.gitignore</code> bloquea <code>.env</code>, <code>venv/</code> y <code>node_modules/</code>.
      </footer>
    </div>
  )
}

export default App
