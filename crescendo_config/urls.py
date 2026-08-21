from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),

    # music.urls must come first: it defines our own login/logout/register views.
    # django.contrib.auth.urls also claims 'login/' and 'logout/', so if it were
    # included first it would shadow them and {% url 'login' %} would resolve to
    # Django's built-in LoginView instead.
    path('', include('music.urls')),

    # Kept for the password-reset / password-change flows.
    path('', include('django.contrib.auth.urls')),
]
