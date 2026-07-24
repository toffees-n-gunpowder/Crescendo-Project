from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Avg


class User(AbstractUser):
    """
    extending django's abstractuser, custom user model
    supports user roles (listener vs artist)
    """
    ACCOUNT_TYPE_CHOICES = (
        ('listener', 'Listener'),
        ('artist', 'Artist'),
    )
    SUBSCRIPTION_TYPE_CHOICES = (
        ('free', 'Free'),
        ('premium', 'Premium'),
    )

    account_type = models.CharField(
        max_length=20,
        choices=ACCOUNT_TYPE_CHOICES,
        default='listener',
        help_text="Designates whether the user is a general listener or a verified artist."
    )
    subscription_type = models.CharField(
        max_length=20,
        choices=SUBSCRIPTION_TYPE_CHOICES,
        default='free',
        help_text="Designates the user's current subscription level."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.username} ({self.get_account_type_display()} - {self.get_subscription_type_display()})"


class Artist(models.Model):
    """
    Represents musical artists or bands in Crescendo.
    Can be optionally claimed by a registered User (OneToOne relationship).
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='artist_profile',
        help_text="Optional link to a User account for artists who claim their profile."
    )
    name = models.CharField(max_length=255)
    bio = models.TextField(blank=True, default='')
    verified = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class Album(models.Model):
    """
    Represents a musical album released by an Artist.
    """
    artist = models.ForeignKey(Artist, on_delete=models.CASCADE, related_name='albums')
    title = models.CharField(max_length=255)
    release_date = models.DateField()
    cover_url = models.URLField(max_length=500, blank=True, default='')

    def __str__(self):
        return f"{self.title} by {self.artist.name}"


class Genre(models.Model):
    """
    Musical genre categorization (e.g. Classical, Pop, Rock, Synthwave).
    """
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class Era(models.Model):
    """
    Categorizes music by time period or historical era (e.g., "1950s", "1960s", "Baroque", "Romantic").
    """
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.name


class Track(models.Model):
    """
    Individual playable audio track linked to an Album, Genre, and optional Era.
    """
    album = models.ForeignKey(Album, on_delete=models.CASCADE, related_name='tracks')
    genre = models.ForeignKey(Genre, on_delete=models.SET_NULL, null=True, blank=True, related_name='tracks')
    era = models.ForeignKey(Era, on_delete=models.SET_NULL, null=True, blank=True, related_name='tracks')
    title = models.CharField(max_length=255)
    duration_sec = models.PositiveIntegerField(help_text="Track duration in seconds")
    track_number = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['album', 'track_number']

    def __str__(self):
        return f"{self.title} - {self.album.artist.name}"

    @property
    def formatted_duration(self):
        minutes = self.duration_sec // 60
        seconds = self.duration_sec % 60
        return f"{minutes}:{seconds:02d}"


class Playlist(models.Model):
    """
    User-created collection of tracks.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='playlists')
    name = models.CharField(max_length=255)
    is_public = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} (by {self.user.username})"


class PlaylistTrack(models.Model):
    """
    Junction model linking a Track to a Playlist with order position.
    """
    playlist = models.ForeignKey(Playlist, on_delete=models.CASCADE, related_name='playlist_tracks')
    track = models.ForeignKey(Track, on_delete=models.CASCADE, related_name='playlist_tracks')
    position = models.PositiveIntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('playlist', 'track')
        ordering = ['position']

    def __str__(self):
        return f"#{self.position} {self.track.title} in {self.playlist.name}"


class PersonalGroup(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank = True, default='')
    is_public = models.BooleanField(default=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    # Add this exact block below your fields
    @property
    def average_rating(self):
        # 1. Look at all reviews linked to this specific group
        # 2. Calculate the average of the 'rating' column
        avg = self.groupreview_set.aggregate(Avg('rating'))['rating__avg']
        
        # 3. If there are no reviews yet, return 0.0. Otherwise, round to 1 decimal place.
        if avg is not None:
            return round(avg, 1)
        return 0.0


class GroupTrack(models.Model):
    """
    Junction model for attaching single tracks directly to a PersonalGroup.
    """
    personal_group = models.ForeignKey(PersonalGroup, on_delete=models.CASCADE, related_name='group_tracks')
    track = models.ForeignKey(Track, on_delete=models.CASCADE, related_name='group_tracks')
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('personal_group', 'track')

    def __str__(self):
        return f"Track '{self.track.title}' in Group '{self.personal_group.name}'"


class GroupPlaylist(models.Model):
    """
    Junction model for attaching entire playlists to a PersonalGroup.
    """
    personal_group = models.ForeignKey(PersonalGroup, on_delete=models.CASCADE, related_name='group_playlists')
    playlist = models.ForeignKey(Playlist, on_delete=models.CASCADE, related_name='group_playlists')
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('personal_group', 'playlist')

    def __str__(self):
        return f"Playlist '{self.playlist.name}' in Group '{self.personal_group.name}'"


class GroupReview(models.Model):
    """
    Model allowing users to rate (1-5 stars) and review PersonalGroups.
    Enforces that private groups can only be reviewed by their owner.
    """
    RATING_CHOICES = [(i, f"{i} Star{'s' if i > 1 else ''}") for i in range(1, 6)]

    group = models.ForeignKey(PersonalGroup, on_delete=models.CASCADE, related_name='reviews')
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='group_reviews')
    rating = models.PositiveSmallIntegerField(choices=RATING_CHOICES)
    review_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('group', 'reviewer')
        ordering = ['-created_at']

    def clean(self):
        super().clean()
        if self.group_id and not self.group.is_public and self.reviewer_id != self.group.owner_id:
            raise ValidationError("You cannot review a private group unless you are the group owner.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.rating}★ Review on '{self.group.name}' by {self.reviewer.username}"


class PlayHistory(models.Model):
    """
    Logs every playback instance of a track by a user.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='play_histories')
    track = models.ForeignKey(Track, on_delete=models.CASCADE, related_name='play_histories')
    played_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Play Histories"
        ordering = ['-played_at']

    def __str__(self):
        return f"{self.user.username} played {self.track.title} at {self.played_at.strftime('%Y-%m-%d %H:%M')}"


class Follow(models.Model):
    """
    Junction model for users following artists.
    """
    follower = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='following')
    artist = models.ForeignKey(Artist, on_delete=models.CASCADE, related_name='followers')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('follower', 'artist')

    def __str__(self):
        return f"{self.follower.username} follows {self.artist.name}"


class LikedTrack(models.Model):
    """
    Junction model for tracks favorited/liked by users.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='liked_tracks')
    track = models.ForeignKey(Track, on_delete=models.CASCADE, related_name='liked_by_users')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'track')

    def __str__(self):
        return f"{self.user.username} liked {self.track.title}"
