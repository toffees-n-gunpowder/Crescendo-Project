from django.urls import path
from . import views

from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    
    # Add these three lines:
    path('register/', views.register_user, name='register'),
    path('login/', views.login_user, name='login'),
    path('logout/', views.logout_user, name='logout'),
    path('like/<int:track_id>/', views.toggle_like, name='toggle_like'),
    path('library/', views.my_library, name='library'),
    path('playlists/', views.playlists, name='playlists'),
    path('playlist/add/<int:track_id>/<int:playlist_id>/', views.add_to_playlist, name='add_to_playlist'),
]