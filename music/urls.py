from django.urls import path

from . import views, views_artist, views_artistpage

urlpatterns = [
    path('', views.home, name='home'),

    path('register/', views.register_user, name='register'),
    path('login/', views.login_user, name='login'),
    path('logout/', views.logout_user, name='logout'),

    path('artist/<int:artist_id>/', views_artistpage.artist_detail, name='artist_detail'),
    path('artist/<int:artist_id>/follow/', views_artistpage.toggle_follow, name='toggle_follow'),

    path('genres/', views.genres, name='genres'),

    path('like/<int:track_id>/', views.toggle_like, name='toggle_like'),
    path('library/', views.my_library, name='library'),
    path('playlists/', views.playlists, name='playlists'),
    path('playlist/add/<int:track_id>/<int:playlist_id>/', views.add_to_playlist, name='add_to_playlist'),
    path('playlist/<int:playlist_id>/', views.playlist_detail, name='playlist_detail'),
    path('playlist/<int:playlist_id>/remove/<int:track_id>/', views.remove_from_playlist, name='remove_from_playlist'),
    path('playlist/<int:playlist_id>/delete/', views.delete_playlist, name='delete_playlist'),
    path('playlist/<int:playlist_id>/rename/', views.rename_playlist, name='rename_playlist'),

    path('dashboard/', views.dashboard, name='dashboard'),

    path('studio/', views_artist.artist_studio, name='artist_studio'),
    path('studio/upload/', views_artist.artist_upload, name='artist_upload'),
    path('studio/profile/', views_artist.artist_update_profile, name='artist_update_profile'),
    path('studio/track/<int:track_id>/delete/', views_artist.artist_delete_track, name='artist_delete_track'),
    path('studio/album/<int:album_id>/delete/', views_artist.artist_delete_album, name='artist_delete_album'),

    path('admin-panel/approvals/', views_artist.admin_approvals, name='admin_approvals'),
    path('admin-panel/approvals/<int:track_id>/', views_artist.admin_review_track, name='admin_review_track'),

    path('admin-panel/', views.admin_panel, name='admin_panel'),
    path('admin-panel/user/<int:user_id>/role/', views.admin_set_role, name='admin_set_role'),
    path('admin-panel/user/<int:user_id>/active/', views.admin_set_active, name='admin_set_active'),
]
