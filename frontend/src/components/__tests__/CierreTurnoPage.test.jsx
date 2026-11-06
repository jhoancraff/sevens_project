import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import CierreTurnoPage from '../CierreTurnoPage';

const linea = (id, extra = {}) => ({
  origen: 'pago',
  origen_id: id,
  fecha_transaccion: '2026-11-06T14:30:00-04:00',
  concepto: `Cobro de nota NE-00${id}`,
  documento: `Nota NE-00${id}`,
  cliente: 'Pedro Pérez',
  numero_cobro: 400 + id,
  saldo_posterior: null,
  referencia: '',
  metodo_pago_id: 1,
  metodo_pago_nombre: 'Efectivo USD',
  moneda: 'USD',
  es_efectivo: true,
  monto_usd: '10.000000',
  monto_bs: null,
  tasa_cambio_referencia: '100.0000',
  ...extra,
});

const pagoMovil = (id) => linea(id, {
  metodo_pago_id: 2,
  metodo_pago_nombre: 'Pago Móvil',
  moneda: 'VES',
  es_efectivo: false,
  monto_usd: '12.000000',
  monto_bs: '1200.00',
  referencia: '4471',
});

function armarApi({ lineas, tipo = 'normal', lotes = [], activo = true, ajenos = [], esPropio = true, cerrar }) {
  const llamadas = [];
  global.fetch = vi.fn((url, opciones = {}) => {
    const ruta = String(url);
    llamadas.push({ ruta, opciones });
    const responder = (cuerpo, ok = true) => Promise.resolve({ ok, json: () => Promise.resolve(cuerpo) });
    if (ruta.includes('cierre-turno/estado')) {
      return responder({ ok: true, activo, umbral_tardio_horas: 20, mis_pendientes: lineas.length, pendientes_ajenos: ajenos, pendientes: ajenos });
    }
    if (ruta.includes('cierre-turno/pendientes')) {
      return responder({
        ok: true,
        activo,
        corte: '2026-11-06T20:00:00-04:00',
        tipo: lineas.length ? tipo : null,
        umbral_tardio_horas: 20,
        titular: { id: 7, nombre: esPropio ? 'Ana' : 'Berta', rol: 'Cajera' },
        es_propio: esPropio,
        lineas,
        lotes_pos_abiertos: lotes,
      });
    }
    if (ruta.includes('cierre-turno/cerrar')) {
      return cerrar ? cerrar(opciones) : responder({ ok: true, message: 'ok', cierre: {} });
    }
    return responder({ ok: false, message: 'ruta inesperada' }, false);
  });
  return llamadas;
}

const botonCerrar = () => screen.getByRole('button', { name: 'Cerrar turno' });

describe('CierreTurnoPage', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('no deja cerrar hasta revisar todas, y exige nota y novedad cuando algo no llegó', async () => {
    armarApi({ lineas: [linea(1), pagoMovil(2)] });
    render(<CierreTurnoPage isMobile={false} onBack={() => {}} />);

    await screen.findByText('Transacciones del turno');
    expect(botonCerrar()).toBeDisabled();
    expect(screen.getByText('Falta revisar 2 transacción(es).')).toBeInTheDocument();

    // Efectivo: atajo "Confirmar todos"; el pago móvil se confirma uno por uno.
    fireEvent.click(screen.getByRole('button', { name: /Confirmar todos \(1\)/ }));
    expect(screen.getByText('Falta revisar 1 transacción(es).')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Confirmar todos/ })).not.toBeInTheDocument();

    const tarjetaMovil = screen.getByText(/Ref: 4471/).closest('article');
    fireEvent.click(within(tarjetaMovil).getByRole('button', { name: /No llegó/ }));
    expect(screen.getByText(/Explica con una nota/)).toBeInTheDocument();

    fireEvent.change(within(tarjetaMovil).getByPlaceholderText(/obligatorio/), { target: { value: 'no aparece en el banco' } });
    expect(screen.getByText(/Escribe la novedad/)).toBeInTheDocument();
    expect(botonCerrar()).toBeDisabled();

    fireEvent.change(screen.getByPlaceholderText(/Obligatoria para este cierre/), { target: { value: 'Un pago móvil sin acreditar' } });
    expect(botonCerrar()).toBeEnabled();
  });

  it('muestra el monto en bolívares con su moneda original para comparar con el banco', async () => {
    armarApi({ lineas: [pagoMovil(2)] });
    render(<CierreTurnoPage isMobile={false} onBack={() => {}} />);
    // El separador de miles/decimales depende del locale del entorno de pruebas.
    expect((await screen.findAllByText(/Bs 1[.,\s]?200[.,]00/)).length).toBeGreaterThan(0);
  });

  it('envía al servidor el titular, el corte, las notas y el estado de cada línea', async () => {
    const llamadas = armarApi({ lineas: [linea(1), pagoMovil(2)] });
    render(<CierreTurnoPage isMobile={false} onBack={() => {}} />);
    await screen.findByText('Transacciones del turno');

    fireEvent.click(screen.getByRole('button', { name: /Confirmar todos/ }));
    const tarjetaMovil = screen.getByText(/Ref: 4471/).closest('article');
    fireEvent.click(within(tarjetaMovil).getByRole('button', { name: /Llegó/ }));
    fireEvent.click(botonCerrar());

    // El modal de confirmacion trae otro boton "Cerrar turno": es el ultimo en el DOM.
    const botones = await screen.findAllByRole('button', { name: 'Cerrar turno' });
    fireEvent.click(botones[botones.length - 1]);

    await waitFor(() => expect(llamadas.some((l) => l.ruta.includes('cierre-turno/cerrar'))).toBe(true));
    const envio = llamadas.find((l) => l.ruta.includes('cierre-turno/cerrar'));
    const cuerpo = JSON.parse(envio.opciones.body);
    expect(envio.opciones.method).toBe('POST');
    expect(cuerpo.titular_id).toBe(7);
    expect(cuerpo.corte).toBe('2026-11-06T20:00:00-04:00');
    expect(cuerpo.lineas).toEqual([
      { origen: 'pago', id: 1, estado: 'confirmada', nota: '' },
      { origen: 'pago', id: 2, estado: 'confirmada', nota: '' },
    ]);
  });

  it('bloquea el cierre y avisa si hay un lote POS abierto', async () => {
    armarApi({ lineas: [linea(1)], lotes: [{ id: 3, numero: 12, metodo_pago_nombre: 'Punto Banesco' }] });
    render(<CierreTurnoPage isMobile={false} onBack={() => {}} />);
    await screen.findByText('Transacciones del turno');
    fireEvent.click(screen.getByRole('button', { name: /Confirmar todos/ }));
    expect(screen.getByText(/#12 \(Punto Banesco\)/)).toBeInTheDocument();
    expect(botonCerrar()).toBeDisabled();
  });

  it('avisa de los turnos ajenos sin cerrar y ofrece cerrar el de esa persona', async () => {
    armarApi({
      lineas: [],
      ajenos: [{ titular_id: 9, titular_nombre: 'Berta', titular_rol: 'Cajera', cantidad: 11, mas_antigua: '2026-11-06T10:00:00-04:00', horas_pendiente: 4, es_mio: false }],
    });
    render(<CierreTurnoPage isMobile={false} onBack={() => {}} />);
    expect(await screen.findByText('Turnos de otras personas sin cerrar')).toBeInTheDocument();
    expect(screen.getByText(/11 sin cerrar/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cerrar su turno' })).toBeInTheDocument();
    expect(screen.getByText('No tienes transacciones pendientes de cierre.')).toBeInTheDocument();
  });

  it('al cerrar el turno de otra persona exige novedad y lo dice', async () => {
    armarApi({ lineas: [linea(1)], tipo: 'por_tercero', esPropio: false });
    render(<CierreTurnoPage isMobile={false} onBack={() => {}} titularInicialId={7} />);
    expect(await screen.findByText(/Estás cerrando el turno de/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Confirmar todos/ }));
    expect(screen.getByText(/Escribe la novedad/)).toBeInTheDocument();
    expect(botonCerrar()).toBeDisabled();
  });

  it('si el cierre de turno no está activado, lo dice y no ofrece cerrar', async () => {
    armarApi({ lineas: [], activo: false });
    render(<CierreTurnoPage isMobile={false} onBack={() => {}} />);
    expect(await screen.findByText(/todavía no está activado/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Cerrar turno' })).not.toBeInTheDocument();
  });
});
