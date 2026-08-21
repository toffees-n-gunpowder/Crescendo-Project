from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='home'),

    # Auth
    path('register/', views.register_user, name='register'),
    path('login/', views.login_user, name='login'),
    path('logout/', views.logout_user, name='logout'),

    # Browsing
    path('genres/', views.genres, name='genres'),

    # Library & playlists
    path('like/<int:track_id>/', views.toggle_like, name='toggle_like'),
    path('library/', views.my_library, name='library'),
    path('playlists/', views.playlists, name='playlists'),
    path('playlist/add/<int:track_id>/<int:playlist_id>/', views.add_to_playlist, name='add_to_playlist'),
    path('playlist/<int:playlist_id>/', views.playlist_detail, name='playlist_detail'),
    path('playlist/<int:playlist_id>/remove/<int:track_id>/', views.remove_from_playlist, name='remove_from_playlist'),
    path('playlist/<int:playlist_id>/delete/', views.delete_playlist, name='delete_playlist'),
    path('playlist/<int:playlist_id>/rename/', views.rename_playlist, name='rename_playlist'),

    path('dashboard/', views.dashboard, name='dashboard'),
]
