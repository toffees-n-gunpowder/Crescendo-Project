from datetime import datetime
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.core.paginator import Paginator
from django.db.models import Count, OuterRef, Subquery
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import CustomUserCreationForm
from .models import Genre, LikedTrack, Playlist, PlaylistTrack, Track, User
from .services import search as search_service

from django.db import connection

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

def dictfetchall(cursor):
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def home(request):
    result = search_service.search_tracks(request.GET)

    liked_track_ids = []
    user_playlists = []
    if request.user.is_authenticated:
        with connection.cursor() as cursor:
            # 1. Fetch liked track IDs for the green heart icons
            cursor.execute(
                "SELECT track_id FROM music_likedtrack WHERE user_id = %s;",
                [request.user.id]
            )
            # Fetchall returns tuples like [(324,), (512,)], so we flatten them with a list comprehension
            liked_track_ids = [row[0] for row in cursor.fetchall()]

            # 2. Fetch user playlists for the "Add to Playlist" dropdown
            cursor.execute(
                "SELECT id, name FROM music_playlist WHERE user_id = %s ORDER BY created_at DESC;",
                [request.user.id]
            )
            user_playlists = dictfetchall(cursor)

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
    with connection.cursor() as cursor:
        # 1. Get the total number of tracks (replaces Track.objects.count())
        cursor.execute("SELECT COUNT(*) FROM music_track;")
        total_tracks = cursor.fetchone()[0]

        # 2. Get genres, count their tracks, and grab one album cover per genre
        cursor.execute("""
            SELECT 
                g.id, 
                g.name, 
                COUNT(t.id) AS track_count,
                (
                    SELECT a.cover_url 
                    FROM music_track sub_t
                    JOIN music_album a ON sub_t.album_id = a.id
                    WHERE sub_t.genre_id = g.id 
                      AND a.cover_url IS NOT NULL 
                      AND a.cover_url != ''
                    LIMIT 1
                ) AS cover_url
            FROM music_genre g
            JOIN music_track t ON g.id = t.genre_id
            GROUP BY g.id, g.name
            ORDER BY track_count DESC, g.name ASC;
        """)
        genre_list = dictfetchall(cursor)

    context = {
        'genre_list': genre_list,
        'total_tracks': total_tracks,
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

    liked_total = 0

    if request.method == 'POST':
        with connection.cursor() as cursor:
            # 1. Manually check if the track actually exists (replacing get_object_or_404)
            cursor.execute("SELECT id FROM music_track WHERE id = %s;", [track_id])
            if not cursor.fetchone():
                raise Http404("Track not found")

            # 2. Check if the user already liked this track
            cursor.execute(
                "SELECT id FROM music_likedtrack WHERE user_id = %s AND track_id = %s;",
                [request.user.id, track_id]
            )
            existing_like = cursor.fetchone()

            if existing_like:
                # 3a. It exists, so UN-LIKE it (Delete)
                cursor.execute(
                    "DELETE FROM music_likedtrack WHERE user_id = %s AND track_id = %s;",
                    [request.user.id, track_id]
                )
                liked = False
            else:
                # 3b. It does not exist, so LIKE it (Insert)
                cursor.execute(
                    "INSERT INTO music_likedtrack (user_id, track_id, created_at) VALUES (%s, %s, %s);",
                    [request.user.id, track_id, datetime.now()]
                )
                liked = True

            # 4. Count the new total likes for the JSON response
            cursor.execute(
                "SELECT COUNT(*) FROM music_likedtrack WHERE user_id = %s;",
                [request.user.id]
            )
            liked_total = cursor.fetchone()[0]

    if _is_ajax(request):
        return JsonResponse({
            'ok': liked is not None,
            'liked': liked,
            'track_id': track_id,
            'liked_total': liked_total,
        })

    # No JavaScript: fall back to bouncing the user back to the page they
    # came from (so from page 2 they don't get kicked back to page 1).
    next_url = request.META.get('HTTP_REFERER', 'home')
    return redirect(next_url)


@login_required(login_url='login')
def my_library(request):
    with connection.cursor() as cursor:
        # 1. Fetch the actual track details by joining the Track table and the LikedTrack table
        cursor.execute("""
            SELECT t.id, t.title, t.duration_sec, t.audio_file, t.album_id 
            FROM music_track t
            JOIN music_likedtrack lt ON t.id = lt.track_id
            WHERE lt.user_id = %s
            ORDER BY lt.created_at DESC;
        """, [request.user.id])
        
        liked_tracks = dictfetchall(cursor)

    # 2. Create a simple list of just the IDs for the green heart icons
    # Notice we use ['id'] like a dictionary now, instead of .id
    liked_track_ids = [track['id'] for track in liked_tracks]

    context = {
        'tracks': liked_tracks,
        'liked_track_ids': liked_track_ids,
    }
    return render(request, 'music/library.html', context)


@login_required(login_url='login')
def playlists(request):
    with connection.cursor() as cursor:
        if request.method == 'POST':
            playlist_name = request.POST.get('name')
            if playlist_name:
                # RAW SQL: Insert a new playlist record
                cursor.execute("""
                    INSERT INTO music_playlist (user_id, name,is_public, created_at) 
                    VALUES (%s,%s,%s, NOW());
                """, [request.user.id, playlist_name,True])
            
            return redirect('playlists')

        # RAW SQL: Fetch all playlists for this user
        cursor.execute("""
            SELECT id, name, created_at 
            FROM music_playlist 
            WHERE user_id = %s 
            ORDER BY created_at DESC;
        """, [request.user.id])
        
        user_playlists = dictfetchall(cursor)

    context = {
        'playlists': user_playlists,
    }
    return render(request, 'music/playlists.html', context)


@login_required(login_url='login')
def add_to_playlist(request, track_id, playlist_id):
    added = None
    playlist_name = ''
    track_title = ''
    track_count = 0

    if request.method == 'POST':
        with connection.cursor() as cursor:
            # 1. Verify playlist belongs to user (Replaces get_object_or_404)
            cursor.execute(
                "SELECT id, name FROM music_playlist WHERE id = %s AND user_id = %s;",
                [playlist_id, request.user.id]
            )
            playlist = cursor.fetchone()
            if not playlist:
                raise Http404("Playlist not found")
            playlist_name = playlist[1] # The 'name' is at index 1 of the tuple (id, name)

            # 2. Verify track exists
            cursor.execute("SELECT id, title FROM music_track WHERE id = %s;", [track_id])
            track = cursor.fetchone()
            if not track:
                raise Http404("Track not found")
            track_title = track[1]

            # 3. Check if track is already in the playlist
            cursor.execute(
                "SELECT 1 FROM music_playlisttrack WHERE playlist_id = %s AND track_id = %s;",
                [playlist_id, track_id]
            )
            exists = cursor.fetchone() is not None

            if not exists:
                # 4. Calculate the track's position (count current tracks + 1)
                cursor.execute(
                    "SELECT COUNT(*) FROM music_playlisttrack WHERE playlist_id = %s;",
                    [playlist_id]
                )
                current_count = cursor.fetchone()[0]

                # 5. Insert the connection!
                cursor.execute("""
                    INSERT INTO music_playlisttrack (playlist_id, track_id, position, added_at)
                    VALUES (%s, %s, %s,NOW());
                """, [playlist_id, track_id, current_count + 1])
                added = True
            else:
                added = False

            # 6. Get the new total track count for the frontend JSON response
            cursor.execute(
                "SELECT COUNT(*) FROM music_playlisttrack WHERE playlist_id = %s;",
                [playlist_id]
            )
            track_count = cursor.fetchone()[0]

    if _is_ajax(request):
        return JsonResponse({
            'ok': added is not None,
            'added': added,
            'already_present': added is False,
            'playlist_id': playlist_id,
            'playlist_name': playlist_name,
            'track_title': track_title,
            'track_count': track_count,
        })

    next_url = request.META.get('HTTP_REFERER', 'home')
    return redirect(next_url)


@login_required(login_url='login')
def playlist_detail(request, playlist_id):
    with connection.cursor() as cursor:
        # 1. Fetch the playlist details
        cursor.execute("""
            SELECT id, name, created_at, is_public 
            FROM music_playlist 
            WHERE id = %s;
        """, [playlist_id])
        
        # We use dictfetchall and grab the first item [0] to make it a dictionary
        playlist_results = dictfetchall(cursor)
        if not playlist_results:
            raise Http404("Playlist not found")
        playlist = playlist_results[0]

        # 2. Fetch the tracks by JOINing the Track table with the Junction table
        cursor.execute("""
            SELECT t.id, t.title, t.duration_sec, t.audio_file, t.album_id, pt.position 
            FROM music_track t
            JOIN music_playlisttrack pt ON t.id = pt.track_id
            WHERE pt.playlist_id = %s
            ORDER BY pt.position ASC;
        """, [playlist_id])
        
        tracks = dictfetchall(cursor)

    # 4. We still want the heart icons to work, so fetch the liked track IDs
    cursor.execute(
            "SELECT track_id FROM music_likedtrack WHERE user_id = %s;",
            [request.user.id]
        )
    liked_track_ids = [row[0] for row in cursor.fetchall()]

    context = {
        'playlist': playlist,
        'tracks': tracks,
        'liked_track_ids': liked_track_ids,
    }
    return render(request, 'music/playlist_detail.html', context)


@login_required(login_url='login')
def remove_from_playlist(request, playlist_id, track_id):
    with connection.cursor() as cursor:
        # 1. Resolve the playlist first (Replaces get_object_or_404)
        cursor.execute(
            "SELECT id FROM music_playlist WHERE id = %s AND user_id = %s;",
            [playlist_id, request.user.id]
        )
        if not cursor.fetchone():
            raise Http404("Playlist not found or access denied")

        if request.method == 'POST':
            # 2. Verify track exists (Replaces get_object_or_404)
            cursor.execute("SELECT id FROM music_track WHERE id = %s;", [track_id])
            if not cursor.fetchone():
                raise Http404("Track not found")

            # 3. Delete the connection (Replaces .delete())
            cursor.execute(
                "DELETE FROM music_playlisttrack WHERE playlist_id = %s AND track_id = %s;",
                [playlist_id, track_id]
            )

    # 4. Redirect using the playlist_id passed in the URL
    return redirect('playlist_detail', playlist_id=playlist_id)


@login_required(login_url='login')
def delete_playlist(request, playlist_id):
    if request.method == 'POST':
        with connection.cursor() as cursor:
            # 1. Security Check: Verify this user actually owns the playlist
            cursor.execute(
                "SELECT id FROM music_playlist WHERE id = %s AND user_id = %s;",
                [playlist_id, request.user.id]
            )
            if not cursor.fetchone():
                raise Http404("Playlist not found or access denied")

            # 2. Delete the child records in the junction table FIRST
            cursor.execute(
                "DELETE FROM music_playlisttrack WHERE playlist_id = %s;",
                [playlist_id]
            )
            
            # 3. Now it is safe to delete the parent playlist!
            cursor.execute(
                "DELETE FROM music_playlist WHERE id = %s;",
                [playlist_id]
            )

    # Send them back to the main Playlists hub
    return redirect('playlists')


@login_required(login_url='login')
def rename_playlist(request, playlist_id):
    with connection.cursor() as cursor:
        # 1. Verify existence and ownership so the redirect works safely
        cursor.execute(
            "SELECT id FROM music_playlist WHERE id = %s AND user_id = %s;",
            [playlist_id, request.user.id]
        )
        if not cursor.fetchone():
            raise Http404("Playlist not found or access denied")

        if request.method == 'POST':
            new_name = request.POST.get('name')
            if new_name:
                # 2. RAW SQL: Update the existing row
                cursor.execute(
                    "UPDATE music_playlist SET name = %s WHERE id = %s AND user_id = %s;",
                    [new_name, playlist_id, request.user.id]
                )

    return redirect('playlist_detail', playlist_id=playlist_id)


@login_required(login_url='login')
def dashboard(request):
    with connection.cursor() as cursor:
        # 1. Count the liked tracks
        cursor.execute(
            "SELECT COUNT(*) FROM music_likedtrack WHERE user_id = %s;",
            [request.user.id]
        )
        liked_count = cursor.fetchone()[0]

        # 2. Count the playlists
        cursor.execute(
            "SELECT COUNT(*) FROM music_playlist WHERE user_id = %s;",
            [request.user.id]
        )
        playlist_count = cursor.fetchone()[0]

    context = {
        'liked_count': liked_count,
        'playlist_count': playlist_count,
    }
    return render(request, 'music/dashboard.html', context)
