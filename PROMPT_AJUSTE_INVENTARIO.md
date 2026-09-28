# Prompt: Implementar módulo "Ajuste de Inventario"

Copia y pega todo este documento como instrucción para el agente de IA (Cline u otro) que vaya a implementar el módulo. Está escrito para que funcione sin necesidad de contexto previo de conversación.

---

## Contexto del proyecto

Repo: `sevens_project` (sistema de restaurante). Stack:
- Backend: Django (carpeta `backend/`), app principal `sevens/`.
- Modelos en `backend/sevens/models/restaurant.py` y `backend/sevens/models/contabilidad.py`, reexportados en `backend/sevens/models/__init__.py`.
- Vistas de negocio separadas por dominio en archivos como `backend/sevens/compras_views.py`, `gastos_views.py`, `devoluciones_views.py`, `facturacion_views.py`, `contabilidad_views.py` (todas usan `@csrf_exempt` + helpers de `auth_helpers.py`).
- Rutas en `backend/sevens/urls.py` (montado bajo `/api/` desde `core/urls.py`).
- Frontend: React (Vite) en `frontend/src/components/*.jsx`, sin router — la navegación es manual vía un estado `activeView` en `frontend/src/components/WelcomeScreen.jsx` (funciones `goToView`/`goBackView`).
- Hooks reutilizables: `useToast`, `useUnsavedChangesGuard`, componentes `ConfirmModal`, `Toast`, `UnsavedChangesModal`.

## Patrón existente a replicar (NO reinventar)

El flujo de "Carga de compra por lote" (`VGCompraBorrador` / `VGDetalleCompraBorrador`) en `backend/sevens/models/restaurant.py` (líneas ~570-622) y sus vistas en `backend/sevens/compras_views.py` son la plantilla exacta a seguir para el nuevo módulo:
- Un borrador único "abierto" compartido, se va agregando líneas una por una vía POST, queda persistido entre sesiones.
- Al confirmar, se convierte en movimientos reales de inventario y el borrador se limpia/cierra.
- El frontend equivalente es `frontend/src/components/AnalystComprasBorradorPage.jsx` (tabla editable + formulario de alta + botón confirmar), y el hub `frontend/src/components/AnalystInventoryHubPage.jsx` donde se agregan las cards de navegación.

Ya existen estos modelos que DEBES reutilizar (no crear duplicados):
- `VGIngrediente` (`backend/sevens/models/restaurant.py` línea ~226): tiene `stock_actual`, `unidad_medida` (choices `g`/`ml`/`unidad`), `costo_unitario`, etc.
- `VGMovimientoInventario` (línea ~653): `TIPOS = [("entrada","Entrada"), ("salida","Salida"), ("ajuste","Ajuste")]`, campos `ingrediente`, `tipo_movimiento`, `cantidad`, `motivo`, `id_referencia` (PositiveIntegerField para enlazar al origen), `compra` (FK opcional), `fecha_movimiento`, `creado_por`. **Todo ajuste de este módulo debe crear registros aquí con `tipo_movimiento='ajuste'` e `id_referencia=<id del ajuste>`.**
- `VGAuditoria` (`backend/sevens/models/base.py`): clase abstracta base con `creado_por`, `actualizado_por`, `fecha_creacion`, `fecha_actualizacion` — todos los modelos nuevos "de cabecera" deben heredar de ella.
- Helpers a reutilizar: `_auth_response` y `_is_admin_user` de `backend/sevens/auth_helpers.py`.

## Requisito funcional (lo que pidió el negocio)

Construir un flujo de **ajuste de inventario** dentro de la sección Contabilidad → Inventario:

1. **Borrador interactivo tipo reporte**: el analista va agregando líneas indicando cuántos gramos/mililitros/unidades se van a **sumar** o **restar** del stock de un ingrediente. Mientras no le den "Guardar", nada afecta el stock real (es solo un borrador).
2. **Guardar**: al presionar guardar, se aplican los cambios pendientes al `stock_actual` de cada ingrediente (sumando o restando según corresponda) y se genera un **ID de nota de ajuste** (el `id` del registro cabecera del ajuste). Cada línea aplicada queda registrada en la tabla de movimientos (`VGMovimientoInventario`, `tipo_movimiento='ajuste'`).
3. **Reglas de edición posteriores a guardar** (la parte más delicada, léela con cuidado):
   - Si después de guardar el analista agrega **otra línea nueva** al mismo ajuste (mismo ID de nota) y vuelve a guardar, **solo esa línea nueva se procesa** — las líneas anteriores que ya fueron aplicadas **no se vuelven a tocar ni reprocesar** (deben quedar "congeladas") salvo que el propio analista decida modificarlas explícitamente.
   - Si el analista **modifica la cantidad de una línea ya aplicada**, el sistema debe calcular la **diferencia** contra lo que ya se había aplicado y generar un **movimiento adicional solo por ese delta** (nunca revertir todo y re-crear desde cero, para no perder trazabilidad).
   - Si el analista **quita/elimina una línea que ya fue aplicada**, el sistema debe **revertir exactamente esa cantidad** (si era una resta del stock, se devuelve al stock; si era una suma, se quita del stock) y dejar registrado ese reverso como un movimiento adicional.
   - Si se quita una línea que **todavía no había sido aplicada** (se agregó al borrador pero nunca se guardó), simplemente se borra sin generar ningún movimiento.
4. **Cierre mensual**: este módulo solo debe permitir crear/editar ajustes **durante el mes en curso**. Debe existir una acción de **"Cerrar mes"** que, una vez ejecutada, bloquea la creación o edición de nuevos ajustes para ese mes (el histórico queda de solo lectura). Intentar agregar/editar/guardar/quitar sobre un mes ya cerrado debe rechazarse con un mensaje claro.
5. **Registro contable**: cada ajuste debe quedar completamente trazado en `VGMovimientoInventario` (la tabla de movimientos general del sistema), igual que ya sucede con las entradas de compras.
6. **Ubicación en la UI**: el módulo debe aparecer como una **nueva card** llamada **"Ajuste de inventario"** dentro del hub de Inventario (`AnalystInventoryHubPage.jsx`), que a su vez cuelga de la sección Contabilidad (ver `ContabilidadPanelPage.jsx`, card `admin-ingredients` → "Inventario").

## Diseño técnico propuesto

(Puedes ajustar detalles si encuentras algo mejor, pero mantén la trazabilidad y las reglas de negocio de arriba.)

### Modelos nuevos

Agregar en `backend/sevens/models/restaurant.py`, junto a los demás modelos de inventario (`VGIngrediente`, `VGMovimientoInventario`):

```python
class VGCierreInventario(VGAuditoria):
    """Cierre mensual del modulo de ajuste de inventario: una vez creado el
    cierre de un anio/mes, ya no se pueden crear ni editar ajustes de ese mes."""
    anio = models.PositiveIntegerField()
    mes = models.PositiveSmallIntegerField()  # 1-12
    fecha_cierre = models.DateTimeField(auto_now_add=True)
    notas = models.TextField(blank=True)

    class Meta:
        db_table = "vg_cierres_inventario"
        unique_together = [("anio", "mes")]
        ordering = ["-anio", "-mes"]


class VGAjusteInventario(VGAuditoria):
    """Cabecera de una nota de ajuste de inventario. El id de este registro
    ES el 'ID de la nota de ajuste' que ve el analista. estado='abierto'
    mientras se pueden seguir agregando/editando lineas; 'confirmado' no
    significa que este cerrado a edicion dentro del mismo mes — solo indica
    que ya tiene al menos una linea aplicada (ver VGDetalleAjusteInventario.aplicado)."""
    ESTADOS = [("abierto", "Abierto"), ("confirmado", "Confirmado")]
    estado = models.CharField(max_length=20, choices=ESTADOS, default="abierto")
    anio = models.PositiveIntegerField()
    mes = models.PositiveSmallIntegerField()
    notas = models.TextField(blank=True)

    class Meta:
        db_table = "vg_ajustes_inventario"
        ordering = ["-fecha_creacion"]


class VGDetalleAjusteInventario(models.Model):
    TIPOS = [("suma", "Suma al stock"), ("resta", "Resta al stock")]
    ajuste = models.ForeignKey(VGAjusteInventario, on_delete=models.CASCADE, related_name="detalles")
    ingrediente = models.ForeignKey(VGIngrediente, on_delete=models.PROTECT, related_name="detalles_ajuste_inventario")
    tipo = models.CharField(max_length=10, choices=TIPOS)
    cantidad = models.DecimalField(max_digits=10, decimal_places=2)
    motivo = models.CharField(max_length=255, blank=True)
    # Cuanto de `cantidad` ya fue efectivamente aplicado al stock (permite
    # reprocesar solo el delta si el analista edita la linea despues de
    # guardada, sin perder trazabilidad).
    cantidad_aplicada = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    aplicado = models.BooleanField(default=False)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "vg_detalle_ajuste_inventario"
```

Reexportar los 3 modelos en `backend/sevens/models/__init__.py` (imports + `__all__`) y registrarlos en `backend/sevens/admin.py` con `admin.ModelAdmin` simples (list_display con los campos clave), siguiendo el estilo ya usado ahí para `VGCompra`/`VGMovimientoInventario`.

### Vistas nuevas

Archivo nuevo `backend/sevens/ajustes_inventario_views.py`, calcado del estilo de `compras_views.py` (todas las funciones `@csrf_exempt`, validando `_is_admin_user`, devolviendo `_auth_response`):

Helpers internos:
- `_mes_actual()` → tupla `(anio, mes)` usando `django.utils.timezone.now()`.
- `_mes_cerrado(anio, mes)` → bool, consulta `VGCierreInventario`.
- `_get_ajuste_abierto(anio, mes)` → el `VGAjusteInventario` en estado `abierto` de ese año/mes (o `None`).
- `_serialize_detalle_ajuste(detalle)` / `_serialize_ajuste(ajuste)`.

Endpoints:
- `admin_ajuste_inventario_view` (GET): devuelve el ajuste abierto del mes actual + histórico de ajustes del mes + estado del cierre del mes.
- `admin_ajuste_inventario_agregar_view` (POST): agrega una línea nueva al borrador (crea el `VGAjusteInventario` si no existe uno abierto para el mes). Valida mes no cerrado, `cantidad > 0`, ingrediente existente y tipo válido.
- `admin_ajuste_inventario_editar_view` (POST): recibe `detalle_id` y nueva `cantidad`/`motivo`. Si `detalle.aplicado` es `False`, solo actualiza el detalle sin tocar stock. Si es `True`, calcula el delta contra `cantidad_aplicada`, mueve `stock_actual` por ese delta (con el signo según `tipo`), crea un `VGMovimientoInventario` adicional indicando que es una corrección, y actualiza `cantidad`/`cantidad_aplicada`.
- `admin_ajuste_inventario_quitar_view` (POST): recibe `detalle_id`. Si `aplicado=False`, borra sin más. Si `aplicado=True`, revierte `cantidad_aplicada` del `stock_actual` (signo inverso a `tipo`), crea un `VGMovimientoInventario` de reverso y elimina el detalle de la lista de pendientes.
- `admin_ajuste_inventario_guardar_view` (POST): recorre las líneas del ajuste abierto con `aplicado=False` (o `cantidad != cantidad_aplicada`), aplica cada delta al `stock_actual`, crea un `VGMovimientoInventario` por línea (`tipo_movimiento='ajuste'`, `cantidad` con signo, `motivo`, `id_referencia=ajuste.id`), marca cada línea `aplicado=True` y `cantidad_aplicada=cantidad`, y deja `ajuste.estado='confirmado'`. El ajuste **sigue existiendo y disponible para agregar más líneas** después (no se cierra solo; eso lo hace el cierre mensual). Debe usar `transaction.atomic()`.
- `admin_ajuste_inventario_descartar_view` (POST): borra el ajuste abierto completo SOLO si ninguna de sus líneas tiene `aplicado=True`. Si ya tiene líneas aplicadas, debe rechazarse y obligar a usar "quitar" línea por línea.
- `admin_cierre_inventario_view` (GET/POST):
  - GET: si el mes actual está cerrado + lista de meses cerrados recientes.
  - POST: crea el `VGCierreInventario` del mes actual. Debe rechazar si hay un ajuste abierto con líneas sin aplicar (`aplicado=False`) pendientes, forzando a guardarlas o quitarlas antes de cerrar.

### Rutas (`backend/sevens/urls.py`)

Importar las funciones nuevas desde `.ajustes_inventario_views` al inicio del archivo (igual que ya se hace con `.compras_views`) y agregar una sección nueva:

```python
    # --- Ajuste de inventario ---------------------------------------------
    path('admin/inventario/ajuste/', admin_ajuste_inventario_view, name='admin_ajuste_inventario'),
    path('admin/inventario/ajuste/agregar/', admin_ajuste_inventario_agregar_view, name='admin_ajuste_inventario_agregar'),
    path('admin/inventario/ajuste/editar/', admin_ajuste_inventario_editar_view, name='admin_ajuste_inventario_editar'),
    path('admin/inventario/ajuste/quitar/', admin_ajuste_inventario_quitar_view, name='admin_ajuste_inventario_quitar'),
    path('admin/inventario/ajuste/guardar/', admin_ajuste_inventario_guardar_view, name='admin_ajuste_inventario_guardar'),
    path('admin/inventario/ajuste/descartar/', admin_ajuste_inventario_descartar_view, name='admin_ajuste_inventario_descartar'),
    path('admin/inventario/cierre/', admin_cierre_inventario_view, name='admin_cierre_inventario'),
```

### Frontend

1. **`frontend/src/components/AnalystInventoryHubPage.jsx`**: agregar una tercera opción al array `options`:
   ```js
   { id: 'adjust', title: 'Ajuste de inventario' }
   ```
   con su handler `adjust: onAdjustInventory` en el objeto `handlers`, siguiendo el mismo patrón que `create`/`view`.

2. **Nuevo componente `frontend/src/components/AnalystAjusteInventarioPage.jsx`**, calcado de `AnalystComprasBorradorPage.jsx`:
   - Carga inicial: `GET /api/admin/catalogo/` (para el buscador de ingredientes, igual que hace compras) + `GET /api/admin/inventario/ajuste/`.
   - Formulario de línea: buscador de ingrediente con autocompletado (mismo patrón `nameQuery`/`nameMatches` de compras), selector `tipo` (suma/resta), input `cantidad`, input `motivo` opcional. Botón "Agregar" contra `admin_ajuste_inventario_agregar_view`.
   - Tabla de líneas del ajuste actual: ingrediente, tipo, cantidad, motivo, y un badge visual que distinga líneas **aplicadas** (con opción "Editar" que permite corregir la cantidad → dispara el delta) de líneas **pendientes** (editables y quitables libremente).
   - Botón "Guardar ajuste" → `POST guardar`; al responder, mostrar con un toast de éxito bien visible el ID de la nota generada (ej. `"Ajuste #123 guardado"`).
   - Sección de histórico del mes: lista de ajustes anteriores del mes (ID + fecha + total de líneas), solo lectura.
   - Si el backend informa que el mes está cerrado, deshabilitar todo el formulario y mostrar un aviso claro (`"El mes de {mes} ya fue cerrado, no se pueden hacer más ajustes"`).
   - Reutilizar `useToast`, `useUnsavedChangesGuard`, `ConfirmModal`, `Toast` y `UnsavedChangesModal` tal como lo hace `AnalystComprasBorradorPage.jsx`.
   - Acción aparte (panel pequeño o botón) para **"Cerrar mes"**, con `ConfirmModal` de confirmación antes de ejecutar, por ser irreversible.

3. **`frontend/src/components/WelcomeScreen.jsx`**:
   - Importar `AnalystAjusteInventarioPage` junto a los demás imports de `Analyst*Page`.
   - En la rama `activeView === 'admin-ingredients'` (donde se renderiza `AnalystInventoryHubPage`), agregar la prop `onAdjustInventory={() => goToView('admin-ingredients-ajuste')}`.
   - Agregar una rama nueva junto a las demás `admin-ingredients-*`:
     ```jsx
     ) : activeView === 'admin-ingredients-ajuste' ? (
       <AnalystAjusteInventarioPage
         isMobile={isMobile}
         onBack={goBackView}
       />
     ```

## Migraciones y validación

1. Ejecutar desde `backend/`: `python manage.py makemigrations sevens` y luego `python manage.py migrate`. Revisa el nombre de la migración autogenerada; no la edites a mano salvo que necesites cargar datos iniciales.
2. Ejecutar `python manage.py check` y confirmar que no hay errores.
3. Probar manualmente el flujo completo (con `runserver` + peticiones fetch/curl o desde la UI):
   - Crear un ajuste, agregar 2 líneas (una suma, una resta) y guardar → verificar `stock_actual` de ambos ingredientes y que se crearon 2 filas en `VGMovimientoInventario` con `tipo_movimiento='ajuste'` e `id_referencia` apuntando al ajuste.
   - Agregar una tercera línea al mismo ajuste (mismo ID) y guardar de nuevo → verificar que **solo** se generó un movimiento nuevo y que los 2 anteriores no se duplicaron.
   - Editar la cantidad de una línea ya aplicada → verificar que se generó un movimiento solo por el delta y que el stock refleja el nuevo total.
   - Quitar una línea ya aplicada → verificar que el stock se revirtió correctamente y que se creó el movimiento de reverso.
   - Cerrar el mes → verificar que agregar una nueva línea (o crear un ajuste nuevo) para ese mes ahora es rechazado por el backend.
4. Si el repo tiene tests de frontend (`frontend/src/components/__tests__/`), correr el comando de test del proyecto (`npm test`) para confirmar que nada existente se rompió.
5. Verificar la navegación: Contabilidad → Inventario → debe aparecer la nueva card "Ajuste de inventario" y abrir la pantalla correctamente.

## Restricciones importantes

- No modificar el comportamiento de `VGCompraBorrador`/`compras_views.py`: son solo la referencia de patrón, no se tocan.
- Mantener el idioma y estilo del proyecto: español, mensajes de error claros, y docstrings/help_text explicando el "por qué" de las decisiones (el proyecto documenta mucho la razón de cada regla — seguir ese estilo).
- Todas las cantidades y montos usan `Decimal`, nunca `float`, siguiendo la convención ya usada en todo el proyecto.
- Las vistas nuevas deben devolver JSON vía `_auth_response` y usar `@csrf_exempt` + verificación manual con `_is_admin_user` (no hay DRF permissions; la autenticación es por sesión custom).
- Cualquier operación que mueva stock debe ir dentro de `transaction.atomic()` para no dejar el inventario a medias.
