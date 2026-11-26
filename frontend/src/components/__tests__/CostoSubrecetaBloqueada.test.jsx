import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import AnalystNewPreparationPage from '../AnalystNewPreparationPage';

const salsa = {
  id: 7, nombre: 'Salsa Sevens', rendimiento_cantidad: '1000', rendimiento_unidad: 'g', bloqueada: true,
  componentes: [], costo_total: null, costo_unitario_calculado: '0.012300',
};

describe('Usar una subreceta bloqueada en otra', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('calcula el costo según la cantidad usada, sin mostrar de qué está hecha', async () => {
    global.fetch = vi.fn(() => Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ ok: true, inventory: [], recipes: [salsa] }),
    }));
    render(<AnalystNewPreparationPage isMobile={false} onBack={() => {}} />);

    fireEvent.focus(await screen.findByPlaceholderText('Buscar subreceta'));
    fireEvent.click(await screen.findByRole('button', { name: 'Salsa Sevens' }));
    fireEvent.change(screen.getAllByPlaceholderText('Cantidad').at(-1), { target: { value: '100' } });
    fireEvent.click(screen.getByRole('button', { name: 'Agregar subreceta' }));

    // 100 g x $0.0123 = $1.23, en la línea del componente y en el total estimado.
    expect(screen.getByText(/Salsa Sevens \(sub_preparacion\) - 100 g · \$0\.0123\/g/)).toHaveTextContent('= $1.23');
    expect(screen.getByText('$1.23')).toBeInTheDocument();
    expect(screen.queryByText(/no incluye las subrecetas bloqueadas/)).not.toBeInTheDocument();
  });
});
