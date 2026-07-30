from django.contrib import admin
from .models import (
    User, Artist, Album, AlbumCredit, Genre, Era, Track, TrackCredit,
    Playlist, PlaylistTrack, PersonalGroup, GroupTrack, GroupPlaylist,
    GroupReview, PlayHistory, Follow, LikedTrack
)

# --- INLINES FOR MANY-TO-MANY RELATIONSHIPS ---
class AlbumCreditInline(admin.TabularInline):
    model = AlbumCredit
    extra = 1

class TrackCreditInline(admin.TabularInline):
    model = TrackCredit
    extra = 1

# --- CUSTOMIZED ADMIN VIEWS ---
@admin.register(Artist)
class ArtistAdmin(admin.ModelAdmin):
    list_display = ('name', 'verified', 'user')
    list_filter = ('verified',)

@admin.register(Album)
class AlbumAdmin(admin.ModelAdmin):
    list_display = ('title', 'release_date')
    inlines = [AlbumCreditInline]  # Allows adding multiple artists directly on the Album page

@admin.register(Track)
class TrackAdmin(admin.ModelAdmin):
    list_display = ('title', 'album', 'duration_sec')
    list_filter = ('genre', 'era')
    inlines = [TrackCreditInline]  # Allows adding primary/featured artists directly on the Track page

@admin.register(PersonalGroup)
class PersonalGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'is_public')
    list_filter = ('is_public',)

# --- BASIC REGISTRATIONS ---
admin.site.register(User)
admin.site.register(Genre)
admin.site.register(Era)
admin.site.register(Playlist)
admin.site.register(PlaylistTrack)
admin.site.register(GroupTrack)
admin.site.register(GroupPlaylist)
admin.site.register(GroupReview)
admin.site.register(PlayHistory)
admin.site.register(Follow)
admin.site.register(LikedTrack)