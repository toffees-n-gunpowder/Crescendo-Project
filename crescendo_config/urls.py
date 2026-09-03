from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

urlpatterns = [
    path('api/', include('music.api.urls')),

    path('', include('music.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
