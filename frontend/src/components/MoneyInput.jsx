import { useState } from 'react';

// Campo de monto. El valor que recibe onChange y el que se guarda en el
// estado/backend es siempre el número limpio ("35602.50"), sin separadores de
// miles: nada del formato viaja al servidor.
//
// Se MUESTRA en formato venezolano (35.602,50): punto para los miles y coma para
// los decimales, igual que el resto de las pantallas. Mientras se escribe, el
// texto se deja tal cual lo teclea la persona (sin reformatearlo en cada tecla) y
// se interpreta con parseMonto, que entiende tanto «2.700,00» como «2700,00»,
// «2,700.00» o «10.50». Al salir del campo se vuelve a mostrar con miles.

// Convierte lo que teclea la persona en el número limpio ("2700.00"). Regla: si
// hay punto y coma, el ÚLTIMO es el decimal; si hay uno solo y le siguen 1 o 2
// dígitos (o es el único separador de un campo con más decimales), es decimal; si
// no, es separador de miles. Con solo 2 decimales «2.700» y «2,700» son 2700.
export function parseMonto(texto, maxDecimales = 2) {
  const s = String(texto ?? '').replace(/[^0-9.,]/g, '');
  if (!s) {
    return '';
  }
  const ultimoPunto = s.lastIndexOf('.');
  const ultimaComa = s.lastIndexOf(',');
  const cuantos = (caracter) => s.split(caracter).length - 1;

  let separadorDecimal = null;
  if (ultimoPunto !== -1 && ultimaComa !== -1) {
    separadorDecimal = ultimoPunto > ultimaComa ? '.' : ',';
  } else if (ultimaComa !== -1 && cuantos(',') === 1) {
    const tras = s.length - ultimaComa - 1;
    // «2,700» con 2 decimales son miles; con más decimales la coma manda como decimal.
    separadorDecimal = tras !== 3 || maxDecimales >= 3 ? ',' : null;
  } else if (ultimoPunto !== -1 && cuantos('.') === 1) {
    const tras = s.length - ultimoPunto - 1;
    // «2.700» con 2 decimales son miles; con más decimales el punto sigue siendo decimal.
    separadorDecimal = tras !== 3 || maxDecimales >= 3 ? '.' : null;
  }

  let entero = s;
  let decimales;
  if (separadorDecimal) {
    const posicion = s.lastIndexOf(separadorDecimal);
    entero = s.slice(0, posicion);
    decimales = s.slice(posicion + 1).replace(/[.,]/g, '');
  }
  entero = entero.replace(/[.,]/g, '').replace(/^0+(?=\d)/, '');
  if (decimales === undefined) {
    return entero;
  }
  if (entero === '') {
    entero = '0';
  }
  return `${entero}.${decimales.slice(0, maxDecimales)}`;
}

// 35602.5 -> «35.602,5». Es lo que se ve cuando el campo no se está editando.
export function formatearVisual(raw) {
  if (raw === '' || raw === null || raw === undefined) {
    return '';
  }
  const [entero, decimales] = String(raw).split('.');
  const conMiles = entero.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  return decimales === undefined ? conMiles : `${conMiles},${decimales}`;
}

// El texto con el que arranca la edición: el número tal cual, con coma decimal y sin
// puntos de miles, para que lo que se teclee a continuación no se confunda con ellos.
function textoDeEdicion(raw) {
  return raw === '' || raw === null || raw === undefined ? '' : String(raw).replace('.', ',');
}

function MoneyInput({ value, onChange, maxDecimales = 2, placeholder = '0,00', style, required, disabled, id }) {
  // null = no se está editando: se muestra el valor con miles. Con texto, se muestra
  // lo que la persona va tecleando mientras siga siendo el mismo valor del padre.
  const [texto, setTexto] = useState(null);
  const valor = value === null || value === undefined ? '' : String(value);
  const visual = texto !== null && parseMonto(texto, maxDecimales) === valor ? texto : formatearVisual(valor);

  const handleChange = (event) => {
    const limpio = event.target.value.replace(/[^0-9.,]/g, '');
    setTexto(limpio);
    onChange(parseMonto(limpio, maxDecimales));
  };

  const handleBlur = () => {
    setTexto(null);
    // «10,» o «10.» sin decimales se guarda como 10.
    if (valor.endsWith('.')) {
      onChange(valor.slice(0, -1));
    }
  };

  return (
    <input
      id={id}
      type="text"
      inputMode="decimal"
      autoComplete="off"
      value={visual}
      onChange={handleChange}
      onFocus={() => setTexto(textoDeEdicion(valor))}
      onBlur={handleBlur}
      placeholder={placeholder}
      style={style}
      required={required}
      disabled={disabled}
    />
  );
}

export default MoneyInput;
