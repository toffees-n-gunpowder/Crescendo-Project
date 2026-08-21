from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.core.paginator import Paginator
from django.db.models import Count, OuterRef, Subquery
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import CustomUserCreationForm
from .models import Genre, LikedTrack, Playlist, PlaylistTrack, Track, User
from .services import search as search_service


def _is_ajax(request):
    """
    True when the browser expects JSON back instead of a redirect.

    Lets the like / add-to-playlist views answer fetch() calls in place while
    still working as plain form posts if JavaScript is unavailable.
    """
    return request.headers.get('x-requested-with') == 'XMLHttpRequest'


def _querystring(request, *drop):
    """
    Rebuild the current query string minus the given keys.

    Lets pagination links carry the active search and filters instead of
    resetting to an unfiltered page 2.
    """
    params = request.GET.copy()
    for key in drop:
        params.pop(key, None)
    encoded = params.urlencode()
    return f'&{encoded}' if encoded else ''


def home(request):
    result = search_service.search_tracks(request.GET)

    liked_track_ids = []
    user_playlists = []
    if request.user.is_authenticated:
        liked_track_ids = list(
            LikedTrack.objects.filter(user=request.user).values_list('track_id', flat=True)
        )
        user_playlists = Playlist.objects.filter(user=request.user)

    paginator = Paginator(result.queryset, 20)
    tracks = paginator.get_page(request.GET.get('page'))

    context = {
        'tracks': tracks,
        'total_results': paginator.count,
        'liked_track_ids': liked_track_ids,
        'user_playlists': user_playlists,
        'filters': result.filters,
        'suggestions': result.suggestions,
        'corrected_from': result.corrected_from,
        'has_active_filters': result.has_active_filters,
        'facets': result.facets,
        'querystring': _querystring(request, 'page'),
    }
    return render(request, 'music/home.html', context)


def genres(request):
    """Browse the catalogue by genre - one card per genre with a track count."""
    # One representative cover per genre, pulled in the same query rather than
    # looping and firing a lookup per genre.
    first_cover = (
        Track.objects
        .filter(genre=OuterRef('pk'))
        .exclude(album__cover_url='')
        .values('album__cover_url')[:1]
    )

    genre_list = (
        Genre.objects
        .annotate(
            track_count=Count('tracks'),
            cover_url=Subquery(first_cover),
        )
        .filter(track_count__gt=0)
        .order_by('-track_count', 'name')
    )

    context = {
        'genre_list': genre_list,
        'total_tracks': Track.objects.count(),
    }
    return render(request, 'music/genres.html', context)


def register_user(request):
    """
    Create the account, then send the user to the login page.

    We deliberately do not auto-login: new users are told to sign up first and
    then sign in, so the credentials they just chose get exercised immediately.
    """
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(
                request,
                f'Welcome to Crescendo, {user.username}! Your account is ready - '
                'please log in with your new username and password.',
            )
            return redirect('login')
        messages.error(request, 'Please fix the errors below and try again.')
    else:
        form = CustomUserCreationForm()

    return render(request, 'registration/register.html', {'form': form})


def login_user(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f'Welcome back, {user.username}.')
            return redirect(request.GET.get('next') or 'home')

        # Distinguish "you typed the wrong password" from "you have no account
        # yet", so a brand new visitor is pointed at Sign Up instead of
        # retrying a password that never existed.
        username = (request.POST.get('username') or '').strip()
        if username and not User.objects.filter(username__iexact=username).exists():
            messages.warning(
                request,
                f'No account found for "{username}". If you are new to Crescendo, '
                'sign up first - it only takes a moment.',
            )
            return render(
                request,
                'registration/login.html',
                {'form': form, 'unknown_user': True, 'attempted_username': username},
            )

        messages.error(request, 'That username and password did not match. Please try again.')
    else:
        form = AuthenticationForm(request)

    return render(request, 'registration/login.html', {'form': form})


def logout_user(request):
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('home')


@login_required(login_url='login')
def toggle_like(request, track_id):
    liked = None

    if request.method == 'POST':
        track = get_object_or_404(Track, id=track_id)

        # Check if this user already liked this specific track
        liked_track = LikedTrack.objects.filter(user=request.user, track=track).first()

        if liked_track:
            # If it exists, they are "un-liking" it. Delete the record.
            liked_track.delete()
            liked = False
        else:
            # If it doesn't exist, they are "liking" it. Create the record.
            LikedTrack.objects.create(user=request.user, track=track)
            liked = True

    if _is_ajax(request):
        return JsonResponse({
            'ok': liked is not None,
            'liked': liked,
            'track_id': track_id,
            'liked_total': LikedTrack.objects.filter(user=request.user).count(),
        })

    # No JavaScript: fall back to bouncing the user back to the page they
    # came from (so from page 2 they don't get kicked back to page 1).
    next_url = request.META.get('HTTP_REFERER', 'home')
    return redirect(next_url)


@login_required(login_url='login')
def my_library(request):
    # 1. Find all the "Like" records for the logged-in user
    liked_records = LikedTrack.objects.filter(user=request.user).select_related('track')

    # 2. Extract just the track information from those records
    liked_tracks = [record.track for record in liked_records]

    # 3. Create a list of the track IDs so the heart icons show up as green
    liked_track_ids = [track.id for track in liked_tracks]

    context = {
        'tracks': liked_tracks,
        'liked_track_ids': liked_track_ids,
    }
    return render(request, 'music/library.html', context)


@login_required(login_url='login')
def playlists(request):
    # If the user submits the "Create Playlist" form:
    if request.method == 'POST':
        playlist_name = request.POST.get('name')
        if playlist_name:
            Playlist.objects.create(user=request.user, name=playlist_name)
        return redirect('playlists')

    # If they are just visiting the page, fetch their playlists:
    user_playlists = Playlist.objects.filter(user=request.user).order_by('-created_at')

    context = {
        'playlists': user_playlists,
    }
    return render(request, 'music/playlists.html', context)


@login_required(login_url='login')
def add_to_playlist(request, track_id, playlist_id):
    added = None
    playlist = None
    track = None

    if request.method == 'POST':
        # 1. Verify the playlist belongs to this user
        playlist = get_object_or_404(Playlist, id=playlist_id, user=request.user)
        track = get_object_or_404(Track, id=track_id)

        # 2. Check if the track is already in the playlist
        exists = PlaylistTrack.objects.filter(playlist=playlist, track=track).exists()

        if not exists:
            # 3. Add it to the playlist
            current_count = playlist.playlist_tracks.count()
            PlaylistTrack.objects.create(
                playlist=playlist,
                track=track,
                position=current_count + 1
            )
            added = True
        else:
            added = False

    if _is_ajax(request):
        return JsonResponse({
            'ok': added is not None,
            'added': added,
            'already_present': added is False,
            'playlist_id': playlist_id,
            'playlist_name': playlist.name if playlist else '',
            'track_title': track.title if track else '',
            'track_count': playlist.playlist_tracks.count() if playlist else 0,
        })

    next_url = request.META.get('HTTP_REFERER', 'home')
    return redirect(next_url)


@login_required(login_url='login')
def playlist_detail(request, playlist_id):
    # 1. Get the specific playlist, ensuring it belongs to the logged-in user
    playlist = get_object_or_404(Playlist, id=playlist_id, user=request.user)

    # 2. Get all the tracks in this playlist, ordered by their position
    playlist_tracks = PlaylistTrack.objects.filter(playlist=playlist).select_related('track').order_by('position')

    # 3. Extract the actual Track objects so the HTML can easily read them
    tracks = [pt.track for pt in playlist_tracks]

    # 4. We still want the heart icons to work, so fetch the liked track IDs
    liked_track_ids = LikedTrack.objects.filter(user=request.user).values_list('track_id', flat=True)

    context = {
        'playlist': playlist,
        'tracks': tracks,
        'liked_track_ids': liked_track_ids,
    }
    return render(request, 'music/playlist_detail.html', context)


@login_required(login_url='login')
def remove_from_playlist(request, playlist_id, track_id):
    # Resolve the playlist first so the redirect below works for GET too.
    playlist = get_object_or_404(Playlist, id=playlist_id, user=request.user)

    if request.method == 'POST':
        track = get_object_or_404(Track, id=track_id)
        PlaylistTrack.objects.filter(playlist=playlist, track=track).delete()

    return redirect('playlist_detail', playlist_id=playlist.id)


@login_required(login_url='login')
def delete_playlist(request, playlist_id):
    if request.method == 'POST':
        # 1. Find the playlist and ensure it belongs to this user
        playlist = get_object_or_404(Playlist, id=playlist_id, user=request.user)
        # 2. Delete it from the database
        playlist.delete()

    # 3. Send them back to the main Playlists hub
    return redirect('playlists')


@login_required(login_url='login')
def rename_playlist(request, playlist_id):
    playlist = get_object_or_404(Playlist, id=playlist_id, user=request.user)

    if request.method == 'POST':
        new_name = request.POST.get('name')
        if new_name:
            playlist.name = new_name
            playlist.save()

    return redirect('playlist_detail', playlist_id=playlist.id)


@login_required(login_url='login')
def dashboard(request):
    # 1. Count how many tracks the user has liked
    liked_count = LikedTrack.objects.filter(user=request.user).count()

    # 2. Count how many playlists the user has created
    playlist_count = Playlist.objects.filter(user=request.user).count()

    context = {
        'liked_count': liked_count,
        'playlist_count': playlist_count,
    }
    return render(request, 'music/dashboard.html', context)
