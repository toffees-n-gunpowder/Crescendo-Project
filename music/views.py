from datetime import datetime
from django.contrib import messages
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render

from .forms import LoginForm, RegistrationForm
from .services import search as search_service
from .db import catalog, core as db_core, playlists as playlist_db, tracks as track_db
from .auth import sessions, users
from .auth.decorators import login_required, role_required

from django.db import connection

def _is_ajax(request):
    return request.headers.get('x-requested-with') == 'XMLHttpRequest'


def _querystring(request, *drop):
    params = request.GET.copy()
    for key in drop:
        params.pop(key, None)
    encoded = params.urlencode()
    return f'&{encoded}' if encoded else ''

def dictfetchall(cursor):
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def home(request):
    result = search_service.search_tracks(
        request.GET, page=request.GET.get('page')
    )

    liked_track_ids = []
    user_playlists = []
    if request.user.is_authenticated:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT track_id FROM music_likedtrack WHERE user_id = %s;",
                [request.user.id]
            )
            liked_track_ids = [row[0] for row in cursor.fetchall()]

            cursor.execute(
                "SELECT id, name FROM music_playlist WHERE user_id = %s ORDER BY created_at DESC;",
                [request.user.id]
            )
            user_playlists = dictfetchall(cursor)

    context = {
        'tracks': result.page,
        'total_results': result.total,
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
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM music_track;")
        total_tracks = cursor.fetchone()[0]

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
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(
                request,
                f'Welcome to Crescendo, {user.username}! Your account is ready - '
                'please log in with your new username and password.',
            )
            return redirect('login')

        clashes = [
            msg
            for field in ('username', 'email')
            for msg in form.errors.get(field, [])
            if 'already' in msg.lower() or 'taken' in msg.lower()
        ]
        status = 409 if clashes else 400
        messages.error(request, 'Please fix the errors below and try again.')
        return render(request, 'registration/register.html',
                      {'form': form}, status=status)

    return render(request, 'registration/register.html',
                  {'form': RegistrationForm()})


def login_user(request):
    if request.method == 'POST':
        form = LoginForm(request.POST)

        if not form.is_valid():
            messages.error(request, 'Please enter both a username and a password.')
            return render(request, 'registration/login.html',
                          {'form': form}, status=400)

        username = form.cleaned_data['username'].strip()
        password = form.cleaned_data['password']

        user = users.authenticate(username, password)

        if user:
            key = sessions.create(
                user.id,
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                ip_address=request.META.get('REMOTE_ADDR', ''),
            )
            users.touch_last_login(user.id)

            messages.success(request, f'Welcome back, {user.username}.')
            response = redirect(request.GET.get('next') or 'home')
            return sessions.set_cookie(response, key)

        if not users.username_exists(username):
            messages.warning(
                request,
                f'No account found for "{username}". If you are new to Crescendo, '
                'sign up first - it only takes a moment.',
            )
            return render(
                request,
                'registration/login.html',
                {'form': form, 'unknown_user': True, 'attempted_username': username},
                status=401,
            )

        messages.error(request, 'That username and password did not match. Please try again.')
        return render(request, 'registration/login.html', {'form': form}, status=401)

    return render(request, 'registration/login.html', {'form': LoginForm()})


def logout_user(request):
    if request.method != 'POST':
        return redirect('home')

    sessions.destroy(getattr(request, 'session_key', None))

    sessions.purge_expired()
    messages.info(request, 'You have been logged out.')
    response = redirect('home')
    return sessions.clear_cookie(response)


@login_required
def toggle_like(request, track_id):
    liked = None

    liked_total = 0

    if request.method == 'POST':
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM music_track WHERE id = %s;", [track_id])
            if not cursor.fetchone():
                raise Http404("Track not found")

            cursor.execute(
                "SELECT id FROM music_likedtrack WHERE user_id = %s AND track_id = %s;",
                [request.user.id, track_id]
            )
            existing_like = cursor.fetchone()

            if existing_like:
                cursor.execute(
                    "DELETE FROM music_likedtrack WHERE user_id = %s AND track_id = %s;",
                    [request.user.id, track_id]
                )
                liked = False
            else:
                cursor.execute(
                    "INSERT INTO music_likedtrack (user_id, track_id, created_at) VALUES (%s, %s, %s);",
                    [request.user.id, track_id, datetime.now()]
                )
                liked = True

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

    next_url = request.META.get('HTTP_REFERER', 'home')
    return redirect(next_url)


@login_required
def my_library(request):
    liked_tracks = db_core.query("""
        SELECT t.id, t.title, t.audio_file, t.duration_sec, t.track_number,
               t.album_id,
               a.title        AS album__title,
               a.cover_url    AS album__cover_url,
               a.release_date AS album__release_date,
               g.name         AS genre__name
        FROM music_likedtrack lt
        JOIN music_track t ON t.id = lt.track_id
        JOIN music_album a ON a.id = t.album_id
        LEFT JOIN music_genre g ON g.id = t.genre_id
        WHERE lt.user_id = %s AND t.approval_status = 'approved'
        ORDER BY lt.created_at DESC
    """, [request.user.id])
    track_db.attach_artists(liked_tracks)

    liked_track_ids = [track.id for track in liked_tracks]

    context = {
        'tracks': liked_tracks,
        'liked_track_ids': liked_track_ids,
    }
    return render(request, 'music/library.html', context)


@login_required
def playlists(request):
    with connection.cursor() as cursor:
        if request.method == 'POST':
            playlist_name = (request.POST.get('name') or '').strip()[:255]
            if playlist_name:
                cursor.execute("""
                    INSERT INTO music_playlist (user_id, name,is_public, created_at)
                    VALUES (%s,%s,%s, NOW());
                """, [request.user.id, playlist_name,True])

            return redirect('playlists')

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


@login_required
def add_to_playlist(request, track_id, playlist_id):
    added = None
    playlist_name = ''
    track_title = ''
    track_count = 0

    if request.method == 'POST':
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, name FROM music_playlist WHERE id = %s AND user_id = %s;",
                [playlist_id, request.user.id]
            )
            playlist = cursor.fetchone()
            if not playlist:
                raise Http404("Playlist not found")
            playlist_name = playlist[1]

            cursor.execute("SELECT id, title FROM music_track WHERE id = %s;", [track_id])
            track = cursor.fetchone()
            if not track:
                raise Http404("Track not found")
            track_title = track[1]

            cursor.execute(
                "SELECT 1 FROM music_playlisttrack WHERE playlist_id = %s AND track_id = %s;",
                [playlist_id, track_id]
            )
            exists = cursor.fetchone() is not None

            if not exists:
                cursor.execute(
                    "SELECT COUNT(*) FROM music_playlisttrack WHERE playlist_id = %s;",
                    [playlist_id]
                )
                current_count = cursor.fetchone()[0]

                cursor.execute("""
                    INSERT INTO music_playlisttrack (playlist_id, track_id, position, added_at)
                    VALUES (%s, %s, %s,NOW());
                """, [playlist_id, track_id, current_count + 1])
                added = True
            else:
                added = False

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


@login_required
def playlist_detail(request, playlist_id):
    playlist = playlist_db.get_owned(playlist_id, request.user.id)
    if not playlist:
        raise Http404('Playlist not found')

    rows = playlist_db.tracks_in(playlist_id, request.user.id)

    context = {
        'playlist': playlist,
        'tracks': rows,
        'track_count': len(rows),
        'liked_track_ids': playlist_db.liked_ids(request.user.id),
    }
    return render(request, 'music/playlist_detail.html', context)


@login_required
def remove_from_playlist(request, playlist_id, track_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM music_playlist WHERE id = %s AND user_id = %s;",
            [playlist_id, request.user.id]
        )
        if not cursor.fetchone():
            raise Http404("Playlist not found or access denied")

        if request.method == 'POST':
            cursor.execute("SELECT id FROM music_track WHERE id = %s;", [track_id])
            if not cursor.fetchone():
                raise Http404("Track not found")

            cursor.execute(
                "DELETE FROM music_playlisttrack WHERE playlist_id = %s AND track_id = %s;",
                [playlist_id, track_id]
            )

    return redirect('playlist_detail', playlist_id=playlist_id)


@login_required
def delete_playlist(request, playlist_id):
    if request.method == 'POST':
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM music_playlist WHERE id = %s AND user_id = %s;",
                [playlist_id, request.user.id]
            )
            if not cursor.fetchone():
                raise Http404("Playlist not found or access denied")

            cursor.execute(
                "DELETE FROM music_playlisttrack WHERE playlist_id = %s;",
                [playlist_id]
            )

            cursor.execute(
                "DELETE FROM music_playlist WHERE id = %s;",
                [playlist_id]
            )

    return redirect('playlists')


@login_required
def rename_playlist(request, playlist_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM music_playlist WHERE id = %s AND user_id = %s;",
            [playlist_id, request.user.id]
        )
        if not cursor.fetchone():
            raise Http404("Playlist not found or access denied")

        if request.method == 'POST':
            new_name = (request.POST.get('name') or '').strip()[:255]
            if new_name:
                cursor.execute(
                    "UPDATE music_playlist SET name = %s WHERE id = %s AND user_id = %s;",
                    [new_name, playlist_id, request.user.id]
                )

    return redirect('playlist_detail', playlist_id=playlist_id)


@login_required
def dashboard(request):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM music_likedtrack WHERE user_id = %s;",
            [request.user.id]
        )
        liked_count = cursor.fetchone()[0]

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


@role_required(users.ROLE_ADMIN)
def admin_panel(request):
    account_rows = users.list_users()
    counts = {row.role: row.count for row in users.role_counts()}

    context = {
        'accounts': account_rows,
        'role_counts': counts,
        'admin_total': users.admin_count(),
        'catalogue': {
            'tracks': catalog.count('music_track'),
            'artists': catalog.count('music_artist'),
            'albums': catalog.count('music_album'),
            'genres': catalog.count('music_genre'),
            'sessions': catalog.count('app_session'),
        },
    }
    return render(request, 'music/admin_panel.html', context)


@role_required(users.ROLE_ADMIN)
def admin_set_role(request, user_id):
    if request.method != 'POST':
        return redirect('admin_panel')

    target = users.get_any_by_id(user_id)
    if not target:
        raise Http404('No such user')

    new_role = (request.POST.get('role') or '').strip()

    if new_role != users.ROLE_ADMIN:
        if target.id == request.user.id:
            messages.error(request, 'You cannot change your own role here.')
            return redirect('admin_panel')
        if (target.is_staff or target.is_superuser) and users.admin_count() <= 1:
            messages.error(request, 'That is the only admin account - promote someone else first.')
            return redirect('admin_panel')

    if new_role == users.ROLE_ADMIN:
        users.promote_to_admin(target.id)
    elif new_role in (users.ROLE_LISTENER, users.ROLE_ARTIST):
        users.set_account_type(target.id, new_role)
    else:
        messages.error(request, 'Unknown role.')
        return redirect('admin_panel')

    messages.success(request, f'{target.username} is now {new_role}.')
    return redirect('admin_panel')


@role_required(users.ROLE_ADMIN)
def admin_set_active(request, user_id):
    if request.method != 'POST':
        return redirect('admin_panel')

    target = users.get_any_by_id(user_id)
    if not target:
        raise Http404('No such user')

    if target.id == request.user.id:
        messages.error(request, 'You cannot deactivate your own account.')
        return redirect('admin_panel')

    activate = request.POST.get('active') == '1'
    users.set_active(target.id, activate)

    if not activate:
        sessions.destroy_all_for_user(target.id)

    messages.success(
        request,
        f'{target.username} {"reactivated" if activate else "deactivated"}.',
    )
    return redirect('admin_panel')
