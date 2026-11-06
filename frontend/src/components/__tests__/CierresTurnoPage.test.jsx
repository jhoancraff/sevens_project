import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import CierresTurnoPage from '../CierresTurnoPage';

const cierre = {
  id: 5,
  codigo: 'CT-000005',
  numero: 5,
  tipo: 'por_tercero',
  tipo_label: 'Cerrado por otra persona',
  titular_id: 7,
  titular_nombre: 'Ana',
  titular_rol: 'Cajera',
  cerrado_por_id: 9,
  cerrado_por_nombre: 'Berta',
  cerrado_por_rol: 'Cajera',
  fecha_cierre: '2026-11-06T15:00:00-04:00',
  desde: '2026-11-06T07:10:00-04:00',
  hasta: '2026-11-06T12:25:00-04:00',
  novedad: 'Ana salió de emergencia',
  total_lineas: 2,
  total_confirmadas: 1,
  total_no_llegaron: 1,
  con_modificaciones: 1,
};

const cambioPosterior = {
  tipo: 'cuenta_cambiada',
  detalle: 'La cuenta pasó de Zelle a Pago Móvil.',
  por: 'Carlos',
  fecha: '2026-11-06T18:00:00-04:00',
  motivo: 'me equivoqué de cuenta',
};

const lineaCerrada = (id, estado, extra = {}) => ({
  id,
  origen: 'pago',
  origen_id: id,
  fecha_transaccion: '2026-11-06T11:00:00-04:00',
  concepto: 'Cobro de nota NE-1',
  documento: 'Nota NE-1',
  cliente: 'Pedro Pérez',
  numero_cobro: 1,
  saldo_posterior: null,
  referencia: '',
  metodo_pago_id: 2,
  metodo_pago_nombre: 'Pago Móvil',
  moneda: 'VES',
  es_efectivo: false,
  monto_usd: '12.000000',
  monto_bs: '1200.00',
  tasa_cambio_referencia: '100.0000',
  estado,
  estado_label: estado === 'confirmada' ? 'Llegó' : 'No llegó',
  nota: estado === 'no_llego' ? 'no aparece en el banco' : '',
  modificaciones: [],
  ...extra,
});

function armarApi({ config = { activo: false, fecha_activacion: null, umbral_tardio_horas: 20 }, impresoraCaida = false } = {}) {
  const llamadas = [];
  global.fetch = vi.fn((url, opciones = {}) => {
    const ruta = String(url);
    llamadas.push({ ruta, opciones });
    const responder = (cuerpo, ok = true) => Promise.resolve({ ok, json: () => Promise.resolve(cuerpo) });
    if (ruta.includes('cierre-turno/imprimir')) {
      return impresoraCaida
        ? responder({ ok: false, message: 'No hay una impresora de caja activa configurada.' }, false)
        : responder({ ok: true, message: 'Acta CT-000005 enviada a la impresora.' });
    }
    if (ruta.includes('cierre_id=')) {
      return responder({ ok: true, cierre: { ...cierre, lineas: [lineaCerrada(1, 'confirmada'), lineaCerrada(2, 'no_llego', { referencia: '4471', modificaciones: [cambioPosterior] })] } });
    }
    if (ruta.includes('cierre-turno/cierres')) {
      const sinCambios = { ...cierre, id: 6, numero: 6, codigo: 'CT-000006', tipo: 'normal', tipo_label: 'Normal', titular_nombre: 'Berta', novedad: '', total_no_llegaron: 0, con_modificaciones: 0 };
      return responder({ ok: true, cierres: [cierre, sinCambios], titulares: [{ id: 7, nombre: 'Ana' }] });
    }
    if (ruta.includes('cierre-turno/estado')) {
      return responder({
        ok: true,
        activo: true,
        umbral_tardio_horas: 20,
        pendientes: [{ titular_id: 7, titular_nombre: 'Ana', titular_rol: 'Cajera', cantidad: 11, mas_antigua: '2026-11-05T10:00:00-04:00', horas_pendiente: 30, es_mio: false }],
      });
    }
    if (ruta.includes('admin/cierre-turno/config')) {
      if (opciones.method === 'POST') {
        return responder({ ok: true, message: 'Cierre de turno activado.', activo: true, fecha_activacion: '2026-11-06', umbral_tardio_horas: 20 });
      }
      return responder({ ok: true, ...config });
    }
    return responder({ ok: false, message: 'ruta inesperada' });
  });
  return llamadas;
}

describe('CierresTurnoPage', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('lista los cierres con su tipo y su novedad, y abre el acta con las líneas que no llegaron', async () => {
    armarApi();
    render(<CierresTurnoPage isMobile={false} onBack={() => {}} esAdmin />);

    expect(await screen.findByText(/CT-000005 · Ana/)).toBeInTheDocument();
    expect(screen.getByText('Novedad: Ana salió de emergencia')).toBeInTheDocument();
    expect(screen.getAllByText('Cerrado por otra persona').length).toBeGreaterThan(0);

    fireEvent.click(screen.getByText(/CT-000005 · Ana/));
    expect(await screen.findByText('Nota: no aparece en el banco')).toBeInTheDocument();
    expect(screen.getByText('No llegó')).toBeInTheDocument();
    expect(screen.getByText('Llegó')).toBeInTheDocument();
  });

  it('marca el cierre y la línea que cambiaron después de cerrar, con quién y por qué', async () => {
    armarApi();
    render(<CierresTurnoPage isMobile={false} onBack={() => {}} esAdmin />);

    expect(await screen.findByText('Modificado después 1')).toBeInTheDocument();
    fireEvent.click(screen.getByText(/CT-000005 · Ana/));
    expect(await screen.findByText(/La cuenta pasó de Zelle a Pago Móvil\./)).toBeInTheDocument();
    expect(screen.getByText(/Lo hizo Carlos/)).toBeInTheDocument();
    expect(screen.getByText(/Motivo: me equivoqué de cuenta/)).toBeInTheDocument();
  });

  it('el filtro de modificados oculta los cierres sin cambios posteriores', async () => {
    armarApi();
    render(<CierresTurnoPage isMobile={false} onBack={() => {}} esAdmin />);
    await screen.findByText(/CT-000005 · Ana/);
    expect(screen.getByText(/CT-000006 · Berta/)).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('Solo modificados después del cierre'));
    expect(screen.getByText(/CT-000005 · Ana/)).toBeInTheDocument();
    expect(screen.queryByText(/CT-000006 · Berta/)).not.toBeInTheDocument();
  });

  it('el acta se puede reimprimir en el ticket y descargar en PDF', async () => {
    const llamadas = armarApi();
    render(<CierresTurnoPage isMobile={false} onBack={() => {}} esAdmin />);
    fireEvent.click(await screen.findByText(/CT-000005 · Ana/));

    expect(await screen.findByRole('button', { name: 'Descargar PDF' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Imprimir ticket' }));

    expect(await screen.findByText('Acta CT-000005 enviada a la impresora.')).toBeInTheDocument();
    const envio = llamadas.find((l) => l.ruta.includes('cierre-turno/imprimir'));
    expect(envio.opciones.method).toBe('POST');
    expect(JSON.parse(envio.opciones.body)).toEqual({ cierre_id: 5 });
  });

  it('si la impresora falla lo dice y deja reintentar', async () => {
    armarApi({ impresoraCaida: true });
    render(<CierresTurnoPage isMobile={false} onBack={() => {}} esAdmin />);
    fireEvent.click(await screen.findByText(/CT-000005 · Ana/));

    fireEvent.click(await screen.findByRole('button', { name: 'Imprimir ticket' }));
    expect(await screen.findByText('No hay una impresora de caja activa configurada.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Imprimir ticket' })).toBeEnabled();
  });

  it('una cajera solo ve la pestaña de cierres', async () => {
    armarApi();
    render(<CierresTurnoPage isMobile={false} onBack={() => {}} esAdmin={false} />);
    await screen.findByText(/CT-000005 · Ana/);
    expect(screen.queryByRole('button', { name: 'Pendientes' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Configuración' })).not.toBeInTheDocument();
  });

  it('el tablero marca a quien pasó el umbral y deja cerrar su turno', async () => {
    armarApi();
    const alCerrar = vi.fn();
    render(<CierresTurnoPage isMobile={false} onBack={() => {}} esAdmin onCerrarTurnoDe={alCerrar} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Pendientes' }));
    expect(await screen.findByText(/Pasó el umbral de 20 h/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar su turno' }));
    expect(alCerrar).toHaveBeenCalledWith(7);
  });

  it('activar el cierre de turno pide confirmación antes de enviar', async () => {
    const llamadas = armarApi();
    render(<CierresTurnoPage isMobile={false} onBack={() => {}} esAdmin />);
    fireEvent.click(await screen.findByRole('button', { name: 'Configuración' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Activar cierre de turno' }));
    expect(llamadas.some((l) => l.opciones.method === 'POST')).toBe(false);

    fireEvent.click(screen.getByRole('button', { name: 'Activar' }));
    await waitFor(() => expect(llamadas.some((l) => l.opciones.method === 'POST')).toBe(true));
    const envio = llamadas.find((l) => l.opciones.method === 'POST');
    expect(JSON.parse(envio.opciones.body)).toEqual({ action: 'activar' });
  });
});
