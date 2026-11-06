import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import ReporteCuadreCajaPage from '../ReporteCuadreCajaPage';

function armarApi() {
  global.fetch = vi.fn(() => Promise.resolve({
    ok: true,
    json: () => Promise.resolve({ ok: true, totales_por_metodo: [], cierre: null, resumen_ventas: {} }),
  }));
}

describe('ReporteCuadreCajaPage · cierre de turno', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('el botón Cerrar turno lleva al cierre de turno propio', async () => {
    armarApi();
    const alCerrarTurno = vi.fn();
    render(<ReporteCuadreCajaPage isMobile={false} onBack={() => {}} onNavigate={() => {}} onCerrarTurno={alCerrarTurno} />);

    fireEvent.click(await screen.findByRole('button', { name: /Cerrar turno/ }));
    expect(alCerrarTurno).toHaveBeenCalledTimes(1);
  });

  it('muestra cuántas transacciones propias quedan sin cerrar y avisa si hay de otros', async () => {
    armarApi();
    const estado = {
      activo: true,
      mis_pendientes: 4,
      pendientes_ajenos: [{ titular_nombre: 'Ana', cantidad: 2 }],
    };
    render(<ReporteCuadreCajaPage isMobile={false} onBack={() => {}} onCerrarTurno={() => {}} cierreTurnoEstado={estado} />);

    const boton = await screen.findByRole('button', { name: /Cerrar turno/ });
    expect(boton).toHaveTextContent('4');
    expect(screen.getByTitle('Ana: 2 sin cerrar')).toBeInTheDocument();
  });

  it('con el cierre de turno inactivo no muestra contadores', async () => {
    armarApi();
    render(<ReporteCuadreCajaPage isMobile={false} onBack={() => {}} onCerrarTurno={() => {}} cierreTurnoEstado={{ activo: false }} />);
    const boton = await screen.findByRole('button', { name: 'Cerrar turno' });
    expect(boton).toBeInTheDocument();
  });

  it('sin la prop no aparece el botón', async () => {
    armarApi();
    render(<ReporteCuadreCajaPage isMobile={false} onBack={() => {}} />);
    await screen.findByText('Cuadre de caja diario');
    expect(screen.queryByRole('button', { name: /Cerrar turno/ })).not.toBeInTheDocument();
  });
});
