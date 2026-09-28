"""
Enrutado de la API del restaurante.

Este modulo se monta bajo el prefijo `/api/` desde core/urls.py, asi que las
rutas se escriben sin ese prefijo (por ejemplo 'auth/login/' produce
/api/auth/login/).

Convenciones de nombres:
- Los endpoints de administracion viven bajo 'admin/'.
- Los reportes de contabilidad cuelgan de 'admin/reportes/'.
- Los recursos de negocio cuelgan de su plural en espanol: pedidos/,
  facturas/, notas-entrega/, compras/, gastos/, devoluciones/.

Al ser paths sin converter `<int:...>`, los nombres literales (cocina, cobro,
borrador) nunca chocan con las rutas parametrizadas.
"""
from django.urls import path

from .api_views import (
    LoginView,
    LogoutView,
    MesaListView,
    ProductoListView,
    SessionStatusView,
    adicionales_disponibles_view,
    admin_catalog_view,
    admin_categorias_view,
    admin_chef_recommendations_view,
    admin_compras_view,
    admin_configuracion_costeo_view,
    admin_ingredientes_bulk_create_view,
    admin_ingredientes_import_view,
    admin_impresora_caja_view,
    admin_mesas_view,
    admin_products_view,
    admin_promotions_view,
    admin_recipes_view,
    admin_users_view,
    compra_detail_view,
    kitchen_order_status_update_view,
    kitchen_orders_view,
    mesa_atendida_mover_view,
    mesas_atendidas_view,
    mesas_ocupadas_view,
    meseros_disponibles_view,
    pedido_create_view,
    pedido_detalle_eliminar_view,
    pedido_detalle_mover_view,
    pedido_detalle_reimprimir_view,
    pedido_detail_view,
    pedido_reimprimir_comanda_view,
    pedido_update_view,
    pedidos_cobro_view,
    pedidos_delivery_view,
    product_image_view,
    promociones_activas_view,
    recomendaciones_chef_activas_view,
    reporte_margen_ganancia_view,
    tasa_cambio_view,
)
from .ajustes_inventario_views import (
    admin_ajuste_inventario_agregar_view,
    admin_ajuste_inventario_descartar_view,
    admin_ajuste_inventario_editar_view,
    admin_ajuste_inventario_guardar_view,
    admin_ajuste_inventario_quitar_view,
    admin_ajuste_inventario_view,
    admin_cierre_inventario_view,
)
from .compras_views import (
    admin_compra_borrador_agregar_view,
    admin_compra_borrador_confirmar_view,
    admin_compra_borrador_descartar_view,
    admin_compra_borrador_editar_view,
    admin_compra_borrador_quitar_view,
    admin_compra_borrador_view,
    compra_abono_view,
    cuentas_por_pagar_view,
)
from .contabilidad_views import (
    admin_metodos_pago_view,
    ingresos_extra_view,
    metodos_pago_activos_view,
    reporte_conciliacion_bancaria_view,
    reporte_cuadre_caja_rango_view,
    reporte_cuadre_caja_view,
    reporte_cuentas_cobradas_dia_view,
    reporte_cuentas_por_cobrar_view,
    reporte_disponibilidad_cuentas_view,
    reporte_estado_resultados_view,
    reporte_movimiento_productos_view,
    reporte_venta_nota_detalle_view,
    reporte_ventas_dia_view,
)
from .devoluciones_views import (
    devolucion_crear_view,
    nota_credito_detail_view,
    notas_credito_view,
)
from .facturacion_views import (
    clientes_buscar_view,
    cuentas_por_cobrar_view,
    datos_fiscales_view,
    factura_abono_view,
    factura_anular_view,
    factura_detail_view,
    factura_reimprimir_view,
    facturas_view,
    nota_entrega_abono_view,
    nota_entrega_detail_view,
    nota_entrega_reimprimir_view,
    notas_entrega_view,
    prefactura_anular_view,
    prefactura_convertir_view,
    prefacturas_view,
)
from .gastos_views import (
    admin_categorias_gasto_view,
    admin_gastos_view,
    gasto_abono_view,
    gasto_detail_view,
)

urlpatterns = [
    # --- Autenticacion (sesion con cookies de Django) ---------------------
    path('auth/login/', LoginView.as_view(), name='auth_login'),
    path('auth/logout/', LogoutView.as_view(), name='auth_logout'),
    path('auth/status/', SessionStatusView.as_view(), name='auth_status'),

    # --- Pedidos ----------------------------------------------------------
    path('pedidos/', pedido_create_view, name='pedido_create'),
    # Las literales van antes que las parametrizadas por claridad; sin
    # converter <int:> no hay ambiguedad real entre 'cocina' y '<id>'.
    path('pedidos/cocina/', kitchen_orders_view, name='kitchen_orders'),
    path('pedidos/cobro/', pedidos_cobro_view, name='pedidos_cobro'),
    path('pedidos/delivery/', pedidos_delivery_view, name='pedidos_delivery'),
    path('pedidos/<int:pedido_id>/estado/', kitchen_order_status_update_view, name='kitchen_order_estado'),
    path('pedidos/<int:pedido_id>/reimprimir-comanda/', pedido_reimprimir_comanda_view, name='pedido_comanda_reimprimir'),
    path('pedidos/<int:pedido_id>/actualizar/', pedido_update_view, name='pedido_update'),
    path('pedidos/<int:pedido_id>/items/<int:detalle_id>/eliminar/', pedido_detalle_eliminar_view, name='pedido_detalle_eliminar'),
    path('pedidos/<int:pedido_id>/items/<int:detalle_id>/mover/', pedido_detalle_mover_view, name='pedido_detalle_mover'),
    path('pedidos/<int:pedido_id>/items/<int:detalle_id>/reimprimir/', pedido_detalle_reimprimir_view, name='pedido_detalle_reimprimir'),
    path('pedidos/<int:pedido_id>/', pedido_detail_view, name='pedido_detail'),

    # --- Mesas ------------------------------------------------------------
    path('mesas/', MesaListView.as_view(), name='mesas_lista'),
    path('mesas/ocupadas/', mesas_ocupadas_view, name='mesas_ocupadas'),
    path('pedidos/mesas-atendidas/', mesas_atendidas_view, name='mesas_atendidas'),
    path('pedidos/mesas-atendidas/mover/', mesa_atendida_mover_view, name='mesa_atendida_mover'),
    path('pedidos/meseros-disponibles/', meseros_disponibles_view, name='meseros_disponibles'),

    # --- Catalogo publico -------------------------------------------------
    path('productos/', ProductoListView.as_view(), name='productos_lista'),
    path('productos/<int:product_id>/imagen/', product_image_view, name='producto_imagen'),
    path('adicionales/', adicionales_disponibles_view, name='adicionales_disponibles'),
    path('promociones/', promociones_activas_view, name='promociones_activas'),
    path('recomendaciones-chef/', recomendaciones_chef_activas_view, name='recomendaciones_chef_activas'),
    path('tasa-cambio/', tasa_cambio_view, name='tasa_cambio'),

    # --- Administracion: catalogo y configuracion -------------------------
    path('admin/catalogo/', admin_catalog_view, name='admin_catalogo'),
    path('admin/productos/', admin_products_view, name='admin_productos'),
    path('admin/recetas/', admin_recipes_view, name='admin_recetas'),
    path('admin/categorias/', admin_categorias_view, name='admin_categorias'),
    path('admin/configuracion-costeo/', admin_configuracion_costeo_view, name='admin_configuracion_costeo'),
    path('admin/promociones/', admin_promotions_view, name='admin_promociones'),
    path('admin/recomendaciones-chef/', admin_chef_recommendations_view, name='admin_recomendaciones_chef'),
    path('admin/impresora-caja/', admin_impresora_caja_view, name='admin_impresora_caja'),
    path('admin/catalogo/importar/', admin_ingredientes_import_view, name='admin_ingredientes_importar'),
    path('admin/catalogo/importar-simple/', admin_ingredientes_bulk_create_view, name='admin_ingredientes_crear'),

    # --- Administracion: personas y mesas ---------------------------------
    path('admin/usuarios/', admin_users_view, name='admin_usuarios'),
    path('admin/mesas/', admin_mesas_view, name='admin_mesas'),

    # --- Administracion: compras -------------------------------------------
    path('admin/compras/borrador/agregar/', admin_compra_borrador_agregar_view, name='admin_compra_borrador_agregar'),
    path('admin/compras/borrador/editar/', admin_compra_borrador_editar_view, name='admin_compra_borrador_editar'),
    path('admin/compras/borrador/quitar/', admin_compra_borrador_quitar_view, name='admin_compra_borrador_quitar'),
    path('admin/compras/borrador/descartar/', admin_compra_borrador_descartar_view, name='admin_compra_borrador_descartar'),
    path('admin/compras/borrador/confirmar/', admin_compra_borrador_confirmar_view, name='admin_compra_borrador_confirmar'),
    path('admin/compras/borrador/', admin_compra_borrador_view, name='admin_compra_borrador'),
    path('admin/compras/', admin_compras_view, name='admin_compras'),
    path('admin/compras/<int:compra_id>/', compra_detail_view, name='compra_detail'),

    # --- Administracion: ajuste de inventario ------------------------------
    path('admin/inventario/ajuste/agregar/', admin_ajuste_inventario_agregar_view, name='admin_ajuste_inventario_agregar'),
    path('admin/inventario/ajuste/editar/', admin_ajuste_inventario_editar_view, name='admin_ajuste_inventario_editar'),
    path('admin/inventario/ajuste/quitar/', admin_ajuste_inventario_quitar_view, name='admin_ajuste_inventario_quitar'),
    path('admin/inventario/ajuste/guardar/', admin_ajuste_inventario_guardar_view, name='admin_ajuste_inventario_guardar'),
    path('admin/inventario/ajuste/descartar/', admin_ajuste_inventario_descartar_view, name='admin_ajuste_inventario_descartar'),
    path('admin/inventario/ajuste/', admin_ajuste_inventario_view, name='admin_ajuste_inventario'),
    path('admin/inventario/cierre/', admin_cierre_inventario_view, name='admin_cierre_inventario'),

    # --- Administracion: gastos --------------------------------------------
    path('admin/categorias-gasto/', admin_categorias_gasto_view, name='admin_categorias_gasto'),
    path('admin/gastos/', admin_gastos_view, name='admin_gastos'),
    path('admin/gastos/<int:gasto_id>/abonos/', gasto_abono_view, name='gasto_abono'),
    path('admin/gastos/<int:gasto_id>/', gasto_detail_view, name='gasto_detail'),

    # --- Administracion: metodos de pago e ingresos extra ------------------
    path('admin/metodos-pago/', admin_metodos_pago_view, name='admin_metodos_pago'),
    path('contabilidad/ingresos-extra/', ingresos_extra_view, name='ingresos_extra'),
    path('metodos-pago/', metodos_pago_activos_view, name='metodos_pago_activos'),

    # --- Reportes ---------------------------------------------------------
    path('admin/reportes/estado-resultados/', reporte_estado_resultados_view, name='reporte_estado_resultados'),
    path('admin/reportes/margen-ganancia/', reporte_margen_ganancia_view, name='reporte_margen_ganancia'),
    path('admin/reportes/cuadre-caja/', reporte_cuadre_caja_view, name='reporte_cuadre_caja'),
    path('admin/reportes/cuadre-caja-rango/', reporte_cuadre_caja_rango_view, name='reporte_cuadre_caja_rango'),
    path('admin/reportes/ventas-dia/', reporte_ventas_dia_view, name='reporte_ventas_dia'),
    path('admin/reportes/ventas-dia/<int:nota_id>/', reporte_venta_nota_detalle_view, name='reporte_venta_nota_detalle'),
    path('admin/reportes/cuentas-por-cobrar/', reporte_cuentas_por_cobrar_view, name='reporte_cuentas_por_cobrar'),
    path('admin/reportes/cuentas-cobradas-dia/', reporte_cuentas_cobradas_dia_view, name='reporte_cuentas_cobradas_dia'),
    path('admin/reportes/disponibilidad-cuentas/', reporte_disponibilidad_cuentas_view, name='reporte_disponibilidad_cuentas'),
    path('admin/reportes/conciliacion-bancaria/', reporte_conciliacion_bancaria_view, name='reporte_conciliacion_bancaria'),
    path('admin/reportes/movimiento-productos/', reporte_movimiento_productos_view, name='reporte_movimiento_productos'),

    # --- Facturacion ------------------------------------------------------
    path('clientes/buscar/', clientes_buscar_view, name='clientes_buscar'),
    path('admin/datos-fiscales/', datos_fiscales_view, name='datos_fiscales'),
    path('prefacturas/', prefacturas_view, name='prefacturas'),
    path('prefacturas/<int:prefactura_id>/convertir/', prefactura_convertir_view, name='prefactura_convertir'),
    path('prefacturas/<int:prefactura_id>/anular/', prefactura_anular_view, name='prefactura_anular'),
    path('facturas/', facturas_view, name='facturas'),
    path('facturas/<int:factura_id>/abonos/', factura_abono_view, name='factura_abono'),
    path('facturas/<int:factura_id>/reimprimir/', factura_reimprimir_view, name='factura_reimprimir'),
    path('facturas/<int:factura_id>/anular/', factura_anular_view, name='factura_anular'),
    path('facturas/<int:factura_id>/', factura_detail_view, name='factura_detail'),
    path('cuentas-por-cobrar/', cuentas_por_cobrar_view, name='cuentas_por_cobrar'),
    path('notas-entrega/', notas_entrega_view, name='notas_entrega'),
    path('notas-entrega/<int:nota_id>/abonos/', nota_entrega_abono_view, name='nota_entrega_abono'),
    path('notas-entrega/<int:nota_id>/reimprimir/', nota_entrega_reimprimir_view, name='nota_entrega_reimprimir'),
    path('notas-entrega/<int:nota_id>/', nota_entrega_detail_view, name='nota_entrega_detail'),

    # --- Devoluciones y notas de credito ----------------------------------
    path('devoluciones/', devolucion_crear_view, name='devolucion_crear'),
    path('notas-credito/', notas_credito_view, name='notas_credito'),
    path('notas-credito/<int:nota_credito_id>/', nota_credito_detail_view, name='nota_credito_detail'),

    # --- Cuentas por pagar ------------------------------------------------
    path('cuentas-por-pagar/', cuentas_por_pagar_view, name='cuentas_por_pagar'),
    path('admin/compras/<int:compra_id>/abonos/', compra_abono_view, name='compra_abono'),
]
