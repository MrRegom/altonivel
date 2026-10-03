from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path, re_path
from django.views.static import serve

from panel.forms import IngresoRutForm

urlpatterns = [
    path("ingresar/", auth_views.LoginView.as_view(authentication_form=IngresoRutForm), name="login"),
    path("salir/", auth_views.LogoutView.as_view(), name="logout"),
    path("admin/", admin.site.urls),
    path("", include("panel.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    # En producción solo se publican el logo y las fotos de productos. Los
    # PDF/XML de facturas se descargan por el panel, que exige sesión.
    urlpatterns += [
        re_path(r"^media/(?P<path>(?:empresa|productos)/.+)$", serve, {"document_root": settings.MEDIA_ROOT}),
    ]
