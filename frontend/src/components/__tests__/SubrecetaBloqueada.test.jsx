import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import AnalystPreparationsReportPage from '../AnalystPreparationsReportPage';

const bloqueada = {
  id: 7, nombre: 'Salsa Sevens', rendimiento_cantidad: '1000', rendimiento_unidad: 'g', bloqueada: true,
  componentes: [], componentes_total: null, costo_total: null, costo_unitario_calculado: '0.012300', es_adicional: false,
};
const normal = {
  id: 8, nombre: 'Pico de gallo', rendimiento_cantidad: '500', rendimiento_unidad: 'g', bloqueada: false,
  componentes: [{ nombre: 'Tomate' }], componentes_total: 1, costo_total: '5.00', costo_unitario_calculado: '0.010000',
};
const receta = {
  nombre: 'Salsa Sevens', rendimiento_cantidad: '1000', rendimiento_unidad: 'g', costo_total: '12.30', costo_unitario: '0.012300',
  componentes: [{ tipo: 'ingrediente', nombre: 'Chile ahumado secreto', cantidad: '137.000', unidad: 'g' }],
};

function armarApi() {
  const intentos = [];
  global.fetch = vi.fn((url, opciones = {}) => {
    const ruta = String(url);
    const responder = (cuerpo, ok = true) => Promise.resolve({ ok, json: () => Promise.resolve(cuerpo) });
    if (ruta.includes('subrecetas/desbloquear')) {
      const cuerpo = JSON.parse(opciones.body);
      intentos.push(cuerpo);
      return cuerpo.codigo === 'Ahumado#7'
        ? responder({ ok: true, subreceta: receta })
        : responder({ ok: false, message: 'Código incorrecto. Quedan 4 intento(s).' }, false);
    }
    if (ruta.includes('admin/catalogo')) return responder({ ok: true, recipes: [bloqueada, normal] });
    return responder({ ok: false }, false);
  });
  return intentos;
}

const pintar = () => render(
  <AnalystPreparationsReportPage isMobile={false} onBack={() => {}} onCreateNew={() => {}} onEdit={() => {}} />,
);

describe('Subrecetas bloqueadas', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('la bloqueada sale con candado, sin costo y sin botones de modificar o eliminar', async () => {
    armarApi();
    pintar();
    expect(await screen.findByText('🔒 Receta bloqueada')).toBeInTheDocument();
    expect(screen.getByText('Costo oculto')).toBeInTheDocument();
    expect(screen.queryByText(/0.0123/)).not.toBeInTheDocument(); // en el listado no se muestra
    expect(screen.getByRole('button', { name: 'Ver receta' })).toBeInTheDocument();
    // Solo la subreceta normal se puede modificar o eliminar.
    expect(screen.getAllByRole('button', { name: 'Modificar' })).toHaveLength(1);
    expect(screen.getAllByRole('button', { name: 'Eliminar' })).toHaveLength(1);
  });

  it('con un código errado no muestra la receta; con el correcto sí, y al cerrar vuelve a pedirlo', async () => {
    const intentos = armarApi();
    pintar();
    fireEvent.click(await screen.findByRole('button', { name: 'Ver receta' }));

    const campo = screen.getByLabelText('Código de acceso');
    fireEvent.change(campo, { target: { value: '1111' } });
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Ver receta' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Código incorrecto');
    expect(screen.queryByText('Chile ahumado secreto')).not.toBeInTheDocument();
    expect(campo).toHaveValue('');

    fireEvent.change(campo, { target: { value: 'Ahumado#7' } });
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Ver receta' }));
    expect(await screen.findByText('Chile ahumado secreto')).toBeInTheDocument();
    expect(intentos.map((i) => i.id)).toEqual([7, 7]);

    fireEvent.click(screen.getByRole('button', { name: 'Cerrar' }));
    await waitFor(() => expect(screen.queryByText('Chile ahumado secreto')).not.toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Ver receta' }));
    expect(screen.getByLabelText('Código de acceso')).toHaveValue('');
    expect(screen.queryByText('Chile ahumado secreto')).not.toBeInTheDocument();
  });
});
