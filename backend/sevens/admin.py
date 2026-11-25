from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.core.exceptions import PermissionDenied

from .subrecetas_bloqueadas import LARGO_MINIMO_CODIGO
from .models import (
    VGAccesoSubreceta, VGUsuario, VGRol, VGMesa, VGCliente, VGCategoriaProducto, VGProducto,
    VGIngrediente, VGPreparacion, VGRecetaPreparacion, VGRecetaProducto,
    VGCompra, VGDetalleCompra, VGMovimientoInventario, VGPedido, VGDetallePedido, VGPago, VGPromocion, VGRecomendacionChef,
    VGAjusteInventario, VGDetalleAjusteInventario, VGCierreInventario,
    VGTransferenciaCuenta,
)


# ---------------------------------------------------------------------------
# VGUsuario ya ES el modelo de usuario (AbstractUser), así que sus campos
# extra van directo en el mismo formulario de "Agregar/editar usuario" de
# siempre — sin secciones aparte ni tablas unidas.
# (DjangoUserAdmin y admin.ModelAdmin/TabularInline son nombres del propio
# framework de Django; las clases que yo defino no usan "Admin"/"Inline".)
# ---------------------------------------------------------------------------
@admin.register(VGUsuario)
class VGUsuarioPanel(DjangoUserAdmin):
    model = VGUsuario
    list_display = DjangoUserAdmin.list_display + ("cedula", "id_role")
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Datos del restaurante", {"fields": ("cedula", "telefono", "fecha_nacimiento", "id_role")}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("Datos del restaurante", {"fields": ("cedula", "telefono", "fecha_nacimiento", "id_role")}),
    )


admin.site.register(VGRol)
admin.site.register(VGMesa)
admin.site.register(VGCliente)
admin.site.register(VGCategoriaProducto)
admin.site.register(VGMovimientoInventario)


class VGRecetaProductoSeccion(admin.TabularInline):
    model = VGRecetaProducto
    extra = 1


@admin.register(VGProducto)
class VGProductoPanel(admin.ModelAdmin):
    list_display = ("nombre", "categoria", "precio_venta", "disponible")
    list_filter = ("categoria", "disponible")
    search_fields = ("nombre",)
    inlines = [VGRecetaProductoSeccion]


class VGRecetaPreparacionSeccion(admin.TabularInline):
    model = VGRecetaPreparacion
    fk_name = "preparacion"
    extra = 1


class VGPreparacionFormulario(forms.ModelForm):
    """Formulario del superusuario: marcar "bloqueada" y poner (o cambiar) el código. El código nunca se muestra."""
    nuevo_codigo = forms.CharField(
        label="Código de acceso", required=False, strip=True,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text=(
            f"Mínimo {LARGO_MINIMO_CODIGO} caracteres. Obligatorio al bloquear por primera vez; déjalo vacío para "
            "conservar el actual. No se puede leer después: si se olvida, escribe uno nuevo."
        ),
    )

    class Meta:
        model = VGPreparacion
        fields = "__all__"

    def clean(self):
        datos = super().clean()
        codigo = datos.get("nuevo_codigo") or ""
        if codigo and len(codigo) < LARGO_MINIMO_CODIGO:
            self.add_error("nuevo_codigo", f"El código debe tener al menos {LARGO_MINIMO_CODIGO} caracteres.")
        if datos.get("bloqueada") and not codigo and not self.instance.codigo_acceso:
            self.add_error("nuevo_codigo", "Para bloquear la subreceta tienes que ponerle un código.")
        return datos

    def save(self, commit=True):
        preparacion = super().save(commit=False)
        codigo = self.cleaned_data.get("nuevo_codigo")
        if not preparacion.bloqueada:
            preparacion.codigo_acceso = ""
        elif codigo:
            preparacion.poner_codigo(codigo)
        if commit:
            preparacion.save()
            self.save_m2m()
        return preparacion


@admin.register(VGPreparacion)
class VGPreparacionPanel(admin.ModelAdmin):
    """
    Recetas secretas: solo un superusuario bloquea, pone el código y ve o cambia una subreceta bloqueada. Para
    cualquier otro usuario del Admin, una bloqueada no muestra sus ingredientes ni su historial y no se toca.
    """
    list_display = ("nombre", "rendimiento_cantidad", "rendimiento_unidad", "bloqueada")
    list_filter = ("bloqueada",)
    search_fields = ("nombre",)
    inlines = [VGRecetaPreparacionSeccion]

    @staticmethod
    def _secreta_para(request, obj):
        return obj is not None and obj.bloqueada and not request.user.is_superuser

    def get_form(self, request, obj=None, change=False, **kwargs):
        if request.user.is_superuser:
            kwargs["form"] = VGPreparacionFormulario
        else:
            kwargs["exclude"] = ["bloqueada"]
        return super().get_form(request, obj, change=change, **kwargs)

    def get_fields(self, request, obj=None):
        campos = ["nombre", "rendimiento_cantidad", "rendimiento_unidad", "es_adicional", "margen_ganancia",
                  "creado_por", "actualizado_por"]
        campos = [c for c in campos if c in {f.name for f in VGPreparacion._meta.fields if f.editable}]
        return campos + ["bloqueada", "nuevo_codigo"] if request.user.is_superuser else campos

    def get_inlines(self, request, obj):
        return [] if self._secreta_para(request, obj) else self.inlines

    def has_change_permission(self, request, obj=None):
        return False if self._secreta_para(request, obj) else super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False if self._secreta_para(request, obj) else super().has_delete_permission(request, obj)

    def delete_queryset(self, request, queryset):
        if not request.user.is_superuser:
            queryset = queryset.filter(bloqueada=False)
        super().delete_queryset(request, queryset)

    def history_view(self, request, object_id, extra_context=None):
        # El historial nombra los componentes que se cambiaron.
        obj = self.get_object(request, object_id)
        if self._secreta_para(request, obj):
            raise PermissionDenied
        return super().history_view(request, object_id, extra_context)


@admin.register(VGAccesoSubreceta)
class VGAccesoSubrecetaPanel(admin.ModelAdmin):
    """Quién abrió (o intentó abrir) una receta secreta. Solo lectura y solo para el superusuario."""
    list_display = ("fecha", "usuario", "preparacion", "exitoso", "ip")
    list_filter = ("exitoso", "preparacion")

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(VGIngrediente)
class VGIngredientePanel(admin.ModelAdmin):
    list_display = ("nombre", "stock_actual", "stock_minimo", "unidad_medida")
    list_filter = ("unidad_medida",)


class VGDetalleCompraSeccion(admin.TabularInline):
    model = VGDetalleCompra
    extra = 1


@admin.register(VGCompra)
class VGCompraPanel(admin.ModelAdmin):
    list_display = ("id", "proveedor_nombre", "fecha_compra", "total", "estado")
    list_filter = ("estado",)
    inlines = [VGDetalleCompraSeccion]


class VGDetallePedidoSeccion(admin.TabularInline):
    model = VGDetallePedido
    extra = 1


class VGPagoSeccion(admin.TabularInline):
    model = VGPago
    extra = 0


@admin.register(VGPedido)
class VGPedidoPanel(admin.ModelAdmin):
    list_display = ("id", "mesa", "usuario", "estado", "total", "fecha_creacion")
    list_filter = ("estado", "tipo_pedido")
    inlines = [VGDetallePedidoSeccion, VGPagoSeccion]

@admin.register(VGPromocion)
class VGPromocionPanel(admin.ModelAdmin):
    list_display = ("titulo", "producto", "tipo_descuento", "valor_descuento", "fecha_inicio", "fecha_fin", "activo")
    list_filter = ("activo", "tipo_descuento")
    search_fields = ("titulo",)


@admin.register(VGRecomendacionChef)
class VGRecomendacionChefPanel(admin.ModelAdmin):
    list_display = ("producto", "fecha", "activo")
    list_filter = ("activo", "fecha")
    search_fields = ("producto__nombre",)


class VGDetalleAjusteInventarioSeccion(admin.TabularInline):
    model = VGDetalleAjusteInventario
    extra = 0


@admin.register(VGAjusteInventario)
class VGAjusteInventarioPanel(admin.ModelAdmin):
    list_display = ("id", "anio", "mes", "estado", "fecha_creacion")
    list_filter = ("estado", "anio", "mes")
    inlines = [VGDetalleAjusteInventarioSeccion]


@admin.register(VGCierreInventario)
class VGCierreInventarioPanel(admin.ModelAdmin):
    list_display = ("anio", "mes", "fecha_cierre")
    list_filter = ("anio", "mes")


@admin.register(VGTransferenciaCuenta)
class VGTransferenciaCuentaPanel(admin.ModelAdmin):
    list_display = ("id", "fecha", "cuenta_origen", "cuenta_destino", "monto_origen", "monto_destino", "monto_usd")
    list_filter = ("moneda_origen", "moneda_destino", "cuenta_origen", "cuenta_destino")
    search_fields = ("concepto", "referencia")
