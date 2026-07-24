from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import (
    User, Artist, Album, Genre, Era, Track, Playlist, PlaylistTrack,
    PersonalGroup, GroupTrack, GroupPlaylist, GroupReview,
    PlayHistory, Follow, LikedTrack
)


@admin.register(User)
class CustomUserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'account_type', 'subscription_type', 'is_staff', 'created_at')
    list_filter = ('account_type', 'subscription_type', 'is_staff', 'is_superuser', 'is_active')
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Crescendo Details', {'fields': ('account_type', 'subscription_type')}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Crescendo Details', {'fields': ('account_type', 'subscription_type')}),
    )
    search_fields = ('username', 'email')


class AlbumInline(admin.TabularInline):
    model = Album
    extra = 1


@admin.register(Artist)
class ArtistAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'verified')
    list_filter = ('verified',)
    search_fields = ('name', 'bio')
    inlines = [AlbumInline]


class TrackInline(admin.TabularInline):
    model = Track
    extra = 1


@admin.register(Album)
class AlbumAdmin(admin.ModelAdmin):
    list_display = ('title', 'artist', 'release_date')
    list_filter = ('release_date', 'artist')
    search_fields = ('title', 'artist__name')
    inlines = [TrackInline]


@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(Era)
class EraAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name',)


@admin.register(Track)
class TrackAdmin(admin.ModelAdmin):
    list_display = ('title', 'album', 'genre', 'era', 'duration_sec', 'track_number')
    list_filter = ('genre', 'era', 'album__artist')
    search_fields = ('title', 'album__title', 'album__artist__name')


class PlaylistTrackInline(admin.TabularInline):
    model = PlaylistTrack
    extra = 1
    raw_id_fields = ('track',)


@admin.register(Playlist)
class PlaylistAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'is_public', 'created_at')
    list_filter = ('is_public', 'created_at')
    search_fields = ('name', 'user__username')
    inlines = [PlaylistTrackInline]


class GroupTrackInline(admin.TabularInline):
    model = GroupTrack
    extra = 1
    raw_id_fields = ('track',)


class GroupPlaylistInline(admin.TabularInline):
    model = GroupPlaylist
    extra = 1
    raw_id_fields = ('playlist',)


class GroupReviewInline(admin.TabularInline):
    model = GroupReview
    extra = 0
    readonly_fields = ('reviewer', 'rating', 'review_text', 'created_at')


@admin.register(PersonalGroup)
class PersonalGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'is_public', 'created_at')
    list_filter = ('is_public', 'created_at')
    search_fields = ('name', 'owner__username', 'description')
    inlines = [GroupTrackInline, GroupPlaylistInline, GroupReviewInline]


@admin.register(GroupReview)
class GroupReviewAdmin(admin.ModelAdmin):
    list_display = ('group', 'reviewer', 'rating', 'created_at')
    list_filter = ('rating', 'created_at')
    search_fields = ('group__name', 'reviewer__username', 'review_text')


@admin.register(PlayHistory)
class PlayHistoryAdmin(admin.ModelAdmin):
    list_display = ('user', 'track', 'played_at')
    list_filter = ('played_at',)
    search_fields = ('user__username', 'track__title')


@admin.register(Follow)
class FollowAdmin(admin.ModelAdmin):
    list_display = ('follower', 'artist', 'created_at')
    search_fields = ('follower__username', 'artist__name')


@admin.register(LikedTrack)
class LikedTrackAdmin(admin.ModelAdmin):
    list_display = ('user', 'track', 'created_at')
    search_fields = ('user__username', 'track__title')
