from django.urls import path

from music.api import views

urlpatterns = [
    path('auth/register/', views.register, name='api_register'),
    path('auth/login/',    views.login,    name='api_login'),
    path('auth/logout/',   views.logout,   name='api_logout'),
    path('me/',            views.me,       name='api_me'),

    path('tracks/',                  views.track_list,   name='api_tracks'),
    path('tracks/<int:track_id>/',   views.track_detail, name='api_track'),
    path('genres/',                  views.genre_list,   name='api_genres'),
    path('artists/<int:artist_id>/', views.artist_detail, name='api_artist'),

    path('playlists/',                    views.playlist_collection, name='api_playlists'),
    path('playlists/<int:playlist_id>/',  views.playlist_detail,     name='api_playlist'),
    path('playlists/<int:playlist_id>/tracks/',
         views.playlist_tracks, name='api_playlist_tracks'),
    path('playlists/<int:playlist_id>/tracks/<int:track_id>/',
         views.playlist_track_detail, name='api_playlist_track'),

    path('me/likes/',                       views.my_likes,      name='api_my_likes'),
    path('tracks/<int:track_id>/like/',     views.track_like,    name='api_track_like'),
    path('artists/<int:artist_id>/follow/', views.artist_follow, name='api_artist_follow'),

    path('studio/tracks/',                 views.studio_tracks,       name='api_studio_tracks'),
    path('studio/tracks/<int:track_id>/',  views.studio_track_detail, name='api_studio_track'),

    path('admin/users/',                    views.admin_users,           name='api_admin_users'),
    path('admin/users/<int:user_id>/',      views.admin_user_detail,     name='api_admin_user'),
    path('admin/approvals/',                views.admin_approvals,       name='api_admin_approvals'),
    path('admin/approvals/<int:track_id>/', views.admin_approval_detail, name='api_admin_approval'),
]
