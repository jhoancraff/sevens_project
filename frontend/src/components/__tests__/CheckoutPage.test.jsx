import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import CheckoutPage from '../CheckoutPage';

const pedido = {
  id: 11,
  mesa: 3,
  mesa_id: 3,
  grupo_id: 11,
  tipo_pedido: 'local',
  total: '20.85',
  cliente: 'Ana',
  cliente_cedula: '12345678',
  cliente_apellido: '',
  mesero: 'Mario',
  creado_en: '2026-11-06T12:00:00-04:00',
  items: [],
};

const cuentaVigente = {
  id: 1,
  codigo: 'PF-000001',
  tasa: '100.0000',
  total: '41.70',
  moneda: 'USD',
  pedido_ids: [11],
  minutos_restantes: 50,
};

const avisoDelServidor = 'La cuenta PF-000001 que se le entregó al cliente es de $41.70, pero ahora el pedido suma $20.85 (diferencia $-20.85).';

function armarApi({ cuenta = cuentaVigente, cobro } = {}) {
  const cobros = [];
  global.fetch = vi.fn((url, opciones = {}) => {
    const ruta = String(url);
    const responder = (cuerpo, ok = true) => Promise.resolve({ ok, json: () => Promise.resolve(cuerpo) });
    if (ruta.includes('/api/pedidos/cobro/') && opciones.method === 'POST') {
      const cuerpo = JSON.parse(opciones.body);
      cobros.push(cuerpo);
      return cobro(cuerpo);
    }
    if (ruta.includes('/api/pedidos/cobro/')) {
      return responder({ ok: true, pedidos: [pedido], prefacturas_tasa_vigente: cuenta ? [cuenta] : [] });
    }
    return responder({ ok: false, message: 'ruta no usada en esta prueba' }, false);
  });
  return cobros;
}

async function elegirMesaYPedido() {
  fireEvent.click(await screen.findByRole('button', { name: /Mesa 3/ }));
  fireEvent.click(await screen.findByLabelText(/Pedido #11/));
}

describe('CheckoutPage · cuenta del cliente que ya no coincide con el pedido', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('avisa antes de emitir cuando la cuenta entregada no suma lo mismo que el pedido', async () => {
    armarApi({ cobro: () => Promise.reject(new Error('no debe cobrar')) });
    render(<CheckoutPage isMobile={false} onBack={() => {}} />);
    await elegirMesaYPedido();

    const aviso = await screen.findByRole('alert');
    expect(aviso).toHaveTextContent('La cuenta PF-000001 que tiene el cliente es de $41.70');
    expect(aviso).toHaveTextContent('el pedido ahora suma $20.85');
  });

  it('si la cuenta coincide con el pedido no muestra ningún aviso', async () => {
    armarApi({ cuenta: { ...cuentaVigente, total: '20.85' }, cobro: () => Promise.reject(new Error('no debe cobrar')) });
    render(<CheckoutPage isMobile={false} onBack={() => {}} />);
    await elegirMesaYPedido();

    await screen.findByText(/Cuenta PF-000001/);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('cuando el servidor frena el cobro pide confirmar y lo reenvía con el monto actual', async () => {
    const cobros = armarApi({
      cobro: (cuerpo) => Promise.resolve(
        cuerpo.confirmar_monto_cuenta
          ? {
            ok: true,
            json: () => Promise.resolve({
              ok: true,
              impreso: true,
              nota_entrega: {
                id: 7, codigo: '00000007', total: '20.85', descuento_monto: '0', pedidos: [11],
                tasa_cambio_referencia: '100.0000', tasa_origen: 'prefactura', tasa_prefactura: 'PF-000001',
              },
            }),
          }
          : { ok: false, json: () => Promise.resolve({ ok: false, cuenta_desactualizada: true, message: avisoDelServidor }) },
      ),
    });
    render(<CheckoutPage isMobile={false} onBack={() => {}} />);
    await elegirMesaYPedido();

    fireEvent.click(screen.getByRole('button', { name: 'Nota de entrega' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Sí, registrar' }));

    // El servidor la frenó: aparece la segunda confirmación con los dos montos y NO se cobró todavía.
    expect(await screen.findByText('La cuenta del cliente cambió')).toBeInTheDocument();
    expect(screen.getByText(/es de \$41\.70, pero ahora el pedido suma \$20\.85/)).toBeInTheDocument();
    expect(cobros).toHaveLength(1);
    expect(cobros[0].confirmar_monto_cuenta).toBe(false);

    fireEvent.click(screen.getByRole('button', { name: 'Registrar por el monto actual' }));
    await waitFor(() => expect(cobros).toHaveLength(2));
    expect(cobros[1].confirmar_monto_cuenta).toBe(true);
    expect(await screen.findByText(/Nota de entrega 00000007 registrada/)).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText('La cuenta del cliente cambió')).not.toBeInTheDocument());
  });

  it('cancelar la confirmación no cobra nada', async () => {
    const cobros = armarApi({
      cobro: () => Promise.resolve({ ok: false, json: () => Promise.resolve({ ok: false, cuenta_desactualizada: true, message: avisoDelServidor }) }),
    });
    render(<CheckoutPage isMobile={false} onBack={() => {}} />);
    await elegirMesaYPedido();

    fireEvent.click(screen.getByRole('button', { name: 'Nota de entrega' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Sí, registrar' }));
    await screen.findByText('La cuenta del cliente cambió');

    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }));
    await waitFor(() => expect(screen.queryByText('La cuenta del cliente cambió')).not.toBeInTheDocument());
    expect(cobros).toHaveLength(1);
  });
});
