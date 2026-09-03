from django.http import QueryDict

from music.api.helpers import (api, artist_json, auth_required, bad_request,
                               body, conflict, created, forbidden, no_content,
                               not_found, ok, playlist_json, require_fields,
                               role_required, track_json, unauthorized,
                               user_json, as_int)
from music.auth import sessions, users
from music.db import artists as artist_db, core, playlists as playlist_db, uploads
from music.db import tracks as track_db
from music.forms import RegistrationForm
from music.services import search as search_service


@api('POST')
def register(request):
    data, err = body(request)
    if err:
        return err

    form = RegistrationForm({
        'username': data.get('username', ''),
        'email': data.get('email', ''),
        'account_type': data.get('account_type', 'listener'),
        'password1': data.get('password', data.get('password1', '')),
        'password2': data.get('password_confirm', data.get('password2',
                              data.get('password', ''))),
    })

    if not form.is_valid():
        clashes = [
            msg
            for field in ('username', 'email')
            for msg in form.errors.get(field, [])
            if 'already' in msg.lower() or 'taken' in msg.lower()
        ]
        if clashes:
            return conflict('; '.join(clashes))
        return bad_request('Validation failed.', fields=form.errors)

    user = form.save()
    return created({'user': user_json(user)}, location=f'/api/users/{user.id}/')


@api('POST')
def login(request):
    data, err = body(request)
    if err:
        return err

    missing = require_fields(data, 'username', 'password')
    if missing:
        return missing

    user = users.authenticate(data['username'].strip(), data['password'])
    if not user:
        return unauthorized('Invalid username or password.')

    token = sessions.create(
        user.id,
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        ip_address=request.META.get('REMOTE_ADDR', ''),
    )
    users.touch_last_login(user.id)

    return ok({
        'token': token,
        'token_type': 'Bearer',
        'expires_in_days': sessions.SESSION_DAYS,
        'user': user_json(user),
    })


@api('POST')
@auth_required
def logout(request):
    token = request.headers.get('authorization', '')[7:].strip()
    sessions.destroy(token)
    return no_content()


@api('GET')
@auth_required
def me(request):
    return ok({'user': {
        'id': request.api_user.id,
        'username': request.api_user.username,
        'email': request.api_user.email,
        'role': request.api_user.role,
    }})


@api('GET')
def track_list(request):
    params = QueryDict(request.META.get('QUERY_STRING', ''))
    result = search_service.search_tracks(params, page=params.get('page'))
    page = result.page

    return ok({
        'count': page.count,
        'page': page.number,
        'pages': page.num_pages,
        'per_page': page.per_page,
        'filters': {k: v for k, v in result.filters.items() if v},
        'corrected_from': result.corrected_from,
        'results': [track_json(row) for row in page.object_list],
    })


@api('GET')
def track_detail(request, track_id):
    rows = track_db.fetch_page(['t.id = %s'], [track_id], 'relevance', 1, 1)
    if not rows:
        return not_found('No such track.')
    return ok({'track': track_json(rows[0])})


@api('GET')
def genre_list(request):
    rows = search_service.facets({k: '' for k in search_service.FILTER_KEYS})
    return ok({'count': len(rows['genres']), 'results': rows['genres']})


@api('GET')
def artist_detail(request, artist_id):
    artist = artist_db.get(artist_id)
    if not artist:
        return not_found('No such artist.')

    stats = artist_db.stats(artist_id)
    return ok({
        'artist': artist_json(artist),
        'stats': {
            'tracks': stats.track_count,
            'albums': stats.album_count,
            'followers': stats.follower_count,
        },
        'tracks': [track_json(r) for r in artist_db.tracks(artist_id, limit=100)],
    })


@api('GET', 'POST')
@auth_required
def playlist_collection(request):
    if request.method == 'GET':
        rows = playlist_db.list_for_user(request.api_user.id)
        return ok({'count': len(rows), 'results': [playlist_json(r) for r in rows]})

    data, err = body(request)
    if err:
        return err
    missing = require_fields(data, 'name')
    if missing:
        return missing

    name = data['name'].strip()[:255]
    playlist_id = playlist_db.create(request.api_user.id, name)
    row = playlist_db.get_owned(playlist_id, request.api_user.id)
    return created({'playlist': playlist_json(row)},
                   location=f'/api/playlists/{playlist_id}/')


@api('GET', 'PATCH', 'DELETE')
@auth_required
def playlist_detail(request, playlist_id):
    playlist = playlist_db.get_owned(playlist_id, request.api_user.id)
    if not playlist:
        return not_found('No such playlist.')

    if request.method == 'GET':
        rows = playlist_db.tracks_in(playlist_id, request.api_user.id)
        return ok({
            'playlist': playlist_json(playlist),
            'track_count': len(rows),
            'tracks': [track_json(r) for r in rows],
        })

    if request.method == 'PATCH':
        data, err = body(request)
        if err:
            return err
        name = (data.get('name') or '').strip()
        if not name:
            return bad_request('Provide a non-empty "name".')
        core.execute(
            'UPDATE music_playlist SET name = %s WHERE id = %s AND user_id = %s',
            [name[:255], playlist_id, request.api_user.id],
        )
        return ok({'playlist': playlist_json(
            playlist_db.get_owned(playlist_id, request.api_user.id))})

    core.execute('DELETE FROM music_playlisttrack WHERE playlist_id = %s', [playlist_id])
    core.execute('DELETE FROM music_playlist WHERE id = %s AND user_id = %s',
                 [playlist_id, request.api_user.id])
    return no_content()


@api('POST')
@auth_required
def playlist_tracks(request, playlist_id):
    if not playlist_db.get_owned(playlist_id, request.api_user.id):
        return not_found('No such playlist.')

    data, err = body(request)
    if err:
        return err
    track_id = as_int(data.get('track_id'))
    if not track_id:
        return bad_request('Provide a numeric "track_id".')

    exists = core.scalar(
        "SELECT 1 FROM music_track WHERE id = %s AND approval_status = 'approved'",
        [track_id])
    if not exists:
        return not_found('No such track.')

    already = core.scalar(
        'SELECT 1 FROM music_playlisttrack WHERE playlist_id = %s AND track_id = %s',
        [playlist_id, track_id])
    if already:
        return conflict('That track is already in this playlist.')

    position = (core.scalar(
        'SELECT COALESCE(MAX(position), 0) + 1 FROM music_playlisttrack WHERE playlist_id = %s',
        [playlist_id]) or 1)
    core.execute(
        """
        INSERT INTO music_playlisttrack (playlist_id, track_id, position, added_at)
        VALUES (%s, %s, %s, NOW())
        """,
        [playlist_id, track_id, position])

    return created({'playlist_id': playlist_id, 'track_id': track_id,
                    'position': position},
                   location=f'/api/playlists/{playlist_id}/')


@api('DELETE')
@auth_required
def playlist_track_detail(request, playlist_id, track_id):
    if not playlist_db.get_owned(playlist_id, request.api_user.id):
        return not_found('No such playlist.')

    removed = core.execute(
        'DELETE FROM music_playlisttrack WHERE playlist_id = %s AND track_id = %s',
        [playlist_id, track_id])
    if not removed:
        return not_found('That track is not in this playlist.')
    return no_content()


@api('GET')
@auth_required
def my_likes(request):
    rows = core.query(
        """
        SELECT t.id FROM music_likedtrack lt
        JOIN music_track t ON t.id = lt.track_id
        WHERE lt.user_id = %s AND t.approval_status = 'approved'
        ORDER BY lt.created_at DESC
        """,
        [request.api_user.id])
    ids = [r.id for r in rows]
    return ok({'count': len(ids), 'track_ids': ids})


@api('PUT', 'DELETE')
@auth_required
def track_like(request, track_id):
    if not core.scalar('SELECT 1 FROM music_track WHERE id = %s', [track_id]):
        return not_found('No such track.')

    if request.method == 'DELETE':
        core.execute('DELETE FROM music_likedtrack WHERE user_id = %s AND track_id = %s',
                     [request.api_user.id, track_id])
        return no_content()

    already = core.scalar(
        'SELECT 1 FROM music_likedtrack WHERE user_id = %s AND track_id = %s',
        [request.api_user.id, track_id])
    if already:
        return ok({'liked': True, 'track_id': track_id})

    core.execute(
        'INSERT INTO music_likedtrack (user_id, track_id, created_at) VALUES (%s, %s, NOW())',
        [request.api_user.id, track_id])
    return created({'liked': True, 'track_id': track_id})


@api('PUT', 'DELETE')
@auth_required
def artist_follow(request, artist_id):
    if not artist_db.get(artist_id):
        return not_found('No such artist.')

    if request.method == 'DELETE':
        core.execute('DELETE FROM music_follow WHERE follower_id = %s AND artist_id = %s',
                     [request.api_user.id, artist_id])
        return no_content()

    if artist_db.is_following(request.api_user.id, artist_id):
        return ok({'following': True, 'artist_id': artist_id})

    artist_db.toggle_follow(request.api_user.id, artist_id)
    return created({'following': True, 'artist_id': artist_id})


@api('GET')
@role_required(users.ROLE_ARTIST, users.ROLE_ADMIN)
def studio_tracks(request):
    rows = uploads.tracks_for_user(request.api_user.id)
    counts = uploads.counts_for_user(request.api_user.id)
    return ok({
        'counts': {'total': counts.total, 'pending': counts.pending,
                   'approved': counts.approved, 'rejected': counts.rejected},
        'results': [{
            'id': r.id, 'title': r.title, 'album': r.album_title,
            'genre': r.genre_name, 'status': r.approval_status,
            'audio_url': r.audio_file, 'submitted_at': r.submitted_at,
            'review_note': r.review_note,
        } for r in rows],
    })


@api('DELETE')
@role_required(users.ROLE_ARTIST, users.ROLE_ADMIN)
def studio_track_detail(request, track_id):
    if not uploads.find_own_track(track_id, request.api_user.id):
        return not_found('No such track of yours.')
    uploads.delete_own_track(track_id, request.api_user.id)
    return no_content()


@api('GET')
@role_required(users.ROLE_ADMIN)
def admin_users(request):
    rows = users.list_users()
    return ok({'count': len(rows), 'results': [user_json(r) for r in rows]})


@api('PATCH')
@role_required(users.ROLE_ADMIN)
def admin_user_detail(request, user_id):
    target = users.get_any_by_id(user_id)
    if not target:
        return not_found('No such user.')

    data, err = body(request)
    if err:
        return err

    if 'role' in data:
        role = str(data['role']).strip()
        if role not in users.ROLES:
            return bad_request(f'role must be one of: {", ".join(users.ROLES)}.')
        if target.id == request.api_user.id and role != users.ROLE_ADMIN:
            return forbidden('You cannot change your own role.')
        if role == users.ROLE_ADMIN:
            users.promote_to_admin(target.id)
        else:
            if (target.is_staff or target.is_superuser) and users.admin_count() <= 1:
                return conflict('That is the only admin account.')
            users.set_account_type(target.id, role)

    if 'is_active' in data:
        active = str(data['is_active']).lower() in ('1', 'true', 'yes')
        if target.id == request.api_user.id and not active:
            return forbidden('You cannot deactivate your own account.')
        users.set_active(target.id, active)
        if not active:
            sessions.destroy_all_for_user(target.id)

    return ok({'user': user_json(users.get_any_by_id(user_id))})


@api('GET')
@role_required(users.ROLE_ADMIN)
def admin_approvals(request):
    status = request.GET.get('status', uploads.PENDING)
    if status not in (uploads.PENDING, uploads.APPROVED, uploads.REJECTED):
        return bad_request('status must be pending, approved or rejected.')

    rows = uploads.review_queue(status)
    return ok({
        'status': status,
        'pending_total': uploads.pending_count(),
        'count': len(rows),
        'results': [{
            'id': r.id, 'title': r.title, 'album': r.album_title,
            'genre': r.genre_name, 'status': r.approval_status,
            'submitted_by': r.submitted_by, 'submitted_at': r.submitted_at,
            'audio_url': r.audio_file,
        } for r in rows],
    })


@api('PATCH')
@role_required(users.ROLE_ADMIN)
def admin_approval_detail(request, track_id):
    track = core.query_one('SELECT id, title FROM music_track WHERE id = %s', [track_id])
    if not track:
        return not_found('No such track.')

    data, err = body(request)
    if err:
        return err

    status = str(data.get('status', '')).strip()
    if status not in (uploads.APPROVED, uploads.REJECTED):
        return bad_request('status must be "approved" or "rejected".')

    uploads.set_review(track_id, status, request.api_user.id,
                       str(data.get('note', ''))[:500])
    return ok({'id': track_id, 'title': track.title, 'status': status})
