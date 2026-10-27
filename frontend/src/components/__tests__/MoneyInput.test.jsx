import { useState } from 'react';
import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import MoneyInput, { formatearVisual, parseMonto } from '../MoneyInput';

describe('parseMonto (2 decimales)', () => {
  it.each([
    ['2.700,00', '2700.00'],
    ['35.602,50', '35602.50'],
    ['2700,00', '2700.00'],
    ['10,80', '10.80'],
    ['142,41', '142.41'],
    ['1.080', '1080'],
    ['2,700', '2700'],
    ['2,700.00', '2700.00'],
    ['10.5', '10.5'],
    ['10.50', '10.50'],
    ['1,5', '1.5'],
    ['1.234.567,89', '1234567.89'],
    ['1,234,567.89', '1234567.89'],
    ['10,', '10.'],
    ['10.', '10.'],
    [',5', '0.5'],
    ['.5', '0.5'],
    ['0010', '10'],
    ['27005', '27005'],
    ['10,555', '10555'],
    ['abc', ''],
    ['', ''],
  ])('«%s» -> «%s»', (entrada, esperado) => {
    expect(parseMonto(entrada, 2)).toBe(esperado);
  });

  it('recorta los decimales de más', () => {
    expect(parseMonto('10,5555', 2)).toBe('10.55');
    expect(parseMonto('10.5555', 2)).toBe('10.55');
    expect(parseMonto('1.234,5678', 2)).toBe('1234.56');
  });
});

describe('parseMonto (más decimales)', () => {
  it.each([
    ['0,123456', '0.123456'],
    ['0.123', '0.123'],
    ['1,234', '1.234'],
    ['1.234,5', '1234.5'],
    ['1.5', '1.5'],
  ])('«%s» -> «%s»', (entrada, esperado) => {
    expect(parseMonto(entrada, 6)).toBe(esperado);
  });
});

describe('formatearVisual', () => {
  it('muestra miles con punto y decimales con coma', () => {
    expect(formatearVisual('35602.5')).toBe('35.602,5');
    expect(formatearVisual('2700')).toBe('2.700');
    expect(formatearVisual('0.123456')).toBe('0,123456');
    expect(formatearVisual('1100.')).toBe('1.100,');
    expect(formatearVisual('')).toBe('');
  });
});

function Probe({ inicial = '' }) {
  const [valor, setValor] = useState(inicial);
  return (
    <>
      <MoneyInput value={valor} onChange={setValor} placeholder="monto" />
      <output data-testid="valor">{valor}</output>
    </>
  );
}

describe('MoneyInput', () => {
  const escribir = (caja, texto) => fireEvent.change(caja, { target: { value: texto } });

  it('entiende los bolívares escritos como en el reporte de Cashea', () => {
    render(<Probe />);
    const caja = screen.getByPlaceholderText('monto');
    fireEvent.focus(caja);
    escribir(caja, '35.602,50');
    expect(screen.getByTestId('valor')).toHaveTextContent('35602.50');
    expect(caja).toHaveValue('35.602,50');
    fireEvent.blur(caja);
    expect(caja).toHaveValue('35.602,50');
  });

  it('muestra con miles al salir y vuelve al número simple al entrar', () => {
    render(<Probe />);
    const caja = screen.getByPlaceholderText('monto');
    fireEvent.focus(caja);
    escribir(caja, '2700');
    expect(caja).toHaveValue('2700');
    fireEvent.blur(caja);
    expect(caja).toHaveValue('2.700');
    fireEvent.focus(caja);
    expect(caja).toHaveValue('2700');
  });

  it('un decimal con punto sigue funcionando', () => {
    render(<Probe />);
    const caja = screen.getByPlaceholderText('monto');
    fireEvent.focus(caja);
    escribir(caja, '10.80');
    expect(screen.getByTestId('valor')).toHaveTextContent('10.80');
    fireEvent.blur(caja);
    expect(caja).toHaveValue('10,80');
  });

  it('una coma o punto final sin decimales se guarda sin él al salir', () => {
    render(<Probe />);
    const caja = screen.getByPlaceholderText('monto');
    fireEvent.focus(caja);
    escribir(caja, '10,');
    expect(screen.getByTestId('valor')).toHaveTextContent('10.');
    fireEvent.blur(caja);
    expect(screen.getByTestId('valor')).toHaveTextContent(/^10$/);
  });

  it('ignora las letras', () => {
    render(<Probe />);
    const caja = screen.getByPlaceholderText('monto');
    fireEvent.focus(caja);
    escribir(caja, '1a2b');
    expect(caja).toHaveValue('12');
    expect(screen.getByTestId('valor')).toHaveTextContent('12');
  });

  it('refleja un valor cambiado desde fuera (por ejemplo «Saldo completo»)', () => {
    const { rerender } = render(<MoneyInput value="" onChange={() => {}} placeholder="monto" />);
    rerender(<MoneyInput value="1234.5" onChange={() => {}} placeholder="monto" />);
    expect(screen.getByPlaceholderText('monto')).toHaveValue('1.234,5');
  });
});
