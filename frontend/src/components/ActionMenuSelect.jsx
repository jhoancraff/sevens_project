// Menu de acciones agrupadas bajo un solo <select> — se usa para no llenar la
// cabecera de un reporte con un boton suelto por cada accion (ej. "nueva
// transferencia" + "historial de transferencias" + "nuevo ingreso" +
// "historial de ingresos" = 4 botones sueltos, desordenado). El <select>
// SIEMPRE queda controlado a value="" (nunca se queda "pegado" en la opcion
// elegida): la primera opcion es un placeholder deshabilitado con el nombre
// de la categoria, las demas son las acciones. Al elegir una, se dispara
// onSelect(value) y el propio re-render del padre (que casi siempre abre un
// modal o navega) ya alcanza para que React vuelva a mostrar el placeholder;
// el reset manual de abajo es solo una red de seguridad por si esa accion no
// causara ningun cambio de estado visible en este arbol.
function ActionMenuSelect({ label, options, onSelect, accentColor }) {
  return (
    <select
      value=""
      onChange={(event) => {
        const value = event.target.value;
        event.target.value = '';
        if (value) {
          onSelect(value);
        }
      }}
      style={selectStyle(accentColor)}
      aria-label={label}
    >
      <option value="" disabled>{label}</option>
      {options.map((option) => (
        <option key={option.value} value={option.value}>{option.label}</option>
      ))}
    </select>
  );
}

const CHEVRON_SVG = 'data:image/svg+xml;utf8,' + encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>',
);

const selectStyle = (accentColor) => ({
  appearance: 'none',
  WebkitAppearance: 'none',
  MozAppearance: 'none',
  border: `1px solid ${accentColor}66`,
  borderRadius: 999,
  padding: '10px 34px 10px 16px',
  background: `${accentColor}24 url("${CHEVRON_SVG}") no-repeat right 12px center`,
  backgroundSize: '14px',
  color: '#fff',
  fontWeight: 700,
  fontSize: 13.5,
  cursor: 'pointer',
});

export default ActionMenuSelect;
