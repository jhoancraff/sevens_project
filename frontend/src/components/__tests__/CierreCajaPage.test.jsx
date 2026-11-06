import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import CierreCajaPage from '../CierreCajaPage';

function armarApi(cierreTurnoPendiente) {
  global.fetch = vi.fn(() => Promise.resolve({
    ok: true,
    json: () => Promise.resolve({
      ok: true,
      cierre: null,
      pos: null,
      efectivo_por_moneda: { bs: '0', usd: '0', bs_en_usd: '0' },
      efectivo_esperado_preview: '0',
      gastos_efectivo_dia: '0',
      cierre_turno_pendiente: cierreTurnoPendiente,
    }),
  }));
}

describe('CierreCajaPage con cierre de turno', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('no deja cerrar la caja mientras queden turnos sin cerrar y ofrece cerrarlos', async () => {
    armarApi({
      activo: true,
      total: 3,
      por_titular: [
        { titular_id: 7, titular_nombre: 'Ana', cantidad: 2 },
        { titular_id: 9, titular_nombre: 'Berta', cantidad: 1 },
      ],
    });
    const alCerrarTurno = vi.fn();
    render(<CierreCajaPage isMobile={false} onBack={() => {}} onCerrarTurnoDe={alCerrarTurno} />);

    expect(await screen.findByText(/quedan 3 transacción\(es\) sin cierre de turno/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cerrar caja del día' })).toBeDisabled();

    fireEvent.click(screen.getAllByRole('button', { name: 'Cerrar su turno' })[1]);
    expect(alCerrarTurno).toHaveBeenCalledWith(9);
  });

  it('sin turnos pendientes deja cerrar la caja', async () => {
    armarApi({ activo: true, total: 0, por_titular: [] });
    render(<CierreCajaPage isMobile={false} onBack={() => {}} />);

    expect(await screen.findByRole('button', { name: 'Cerrar caja del día' })).toBeEnabled();
    expect(screen.queryByText(/sin cierre de turno/)).not.toBeInTheDocument();
  });

  it('con el cierre de turno sin activar, la caja se cierra como siempre', async () => {
    armarApi({ activo: false, total: 0, por_titular: [] });
    render(<CierreCajaPage isMobile={false} onBack={() => {}} />);

    expect(await screen.findByRole('button', { name: 'Cerrar caja del día' })).toBeEnabled();
  });
});
