import os
import uuid
from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.core.files.storage import default_storage
from django.http import Http404
from django.shortcuts import redirect, render

from .auth import users
from .auth.decorators import role_required
from .db import catalog, core as db_core, uploads
from .forms import ArtistProfileForm, TrackUploadForm


def _display_name(request):
    profile = uploads.profile_for_user(request.user.id)
    return profile.name if profile else request.user.username


def _delete_audio_file(audio_url):
    if not audio_url or not audio_url.startswith(settings.MEDIA_URL):
        return
    relative = audio_url[len(settings.MEDIA_URL):]
    if default_storage.exists(relative):
        default_storage.delete(relative)


@role_required(users.ROLE_ARTIST, users.ROLE_ADMIN)
def artist_studio(request):
    profile_id = uploads.get_or_create_profile(request.user.id, _display_name(request))
    profile = uploads.profile_for_user(request.user.id)

    albums = uploads.albums_for_user(request.user.id)
    genres = catalog.genre_counts()

    context = {
        'profile': profile,
        'profile_id': profile_id,
        'albums': albums,
        'tracks': uploads.tracks_for_user(request.user.id),
        'counts': uploads.counts_for_user(request.user.id),
        'upload_form': TrackUploadForm(albums=albums, genres=genres),
        'profile_form': ArtistProfileForm(initial={
            'name': profile.name if profile else '',
            'bio': profile.bio if profile else '',
        }),
    }
    return render(request, 'music/artist_studio.html', context)


@role_required(users.ROLE_ARTIST, users.ROLE_ADMIN)
def artist_upload(request):
    if request.method != 'POST':
        return redirect('artist_studio')

    albums = uploads.albums_for_user(request.user.id)
    genres = catalog.genre_counts()
    form = TrackUploadForm(request.POST, request.FILES, albums=albums, genres=genres)

    if not form.is_valid():
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f'{field}: {error}')
        return redirect('artist_studio')

    data = form.cleaned_data
    profile_id = uploads.get_or_create_profile(request.user.id, _display_name(request))

    upload = data['audio']
    extension = os.path.splitext(upload.name)[1].lower()
    saved_path = default_storage.save(f'uploads/{uuid.uuid4().hex}{extension}', upload)
    audio_url = settings.MEDIA_URL + saved_path

    if data['album_choice']:
        album_id = int(data['album_choice'])
    else:
        album_id = uploads.create_album(
            data['new_album_title'].strip(),
            datetime.now().date(),
            '',
            request.user.id,
            profile_id,
        )

    genre_id = catalog.get_or_create_genre(data['genre']) if data.get('genre') else None

    uploads.create_pending_track(
        title=data['title'].strip(),
        album_id=album_id,
        genre_id=genre_id,
        duration_sec=data.get('duration_sec') or 0,
        audio_url=audio_url,
        submitted_by=request.user.id,
        artist_id=profile_id,
        track_number=uploads.next_track_number(album_id),
    )

    messages.success(
        request,
        f'"{data["title"]}" uploaded and sent for review. '
        'It becomes public once an admin approves it.',
    )
    return redirect('artist_studio')


@role_required(users.ROLE_ARTIST, users.ROLE_ADMIN)
def artist_update_profile(request):
    if request.method != 'POST':
        return redirect('artist_studio')

    form = ArtistProfileForm(request.POST)
    if form.is_valid():
        uploads.get_or_create_profile(request.user.id, form.cleaned_data['name'])
        uploads.update_profile(request.user.id, form.cleaned_data['name'],
                               form.cleaned_data.get('bio', ''))
        messages.success(request, 'Artist profile updated.')
    else:
        messages.error(request, 'Could not update the profile.')
    return redirect('artist_studio')


@role_required(users.ROLE_ARTIST, users.ROLE_ADMIN)
def artist_delete_track(request, track_id):
    if request.method != 'POST':
        return redirect('artist_studio')

    track = uploads.find_own_track(track_id, request.user.id)
    if not track:
        raise Http404('No such track')

    _delete_audio_file(track.audio_file)
    uploads.delete_own_track(track_id, request.user.id)

    messages.success(request, f'Deleted "{track.title}".')
    return redirect('artist_studio')


@role_required(users.ROLE_ARTIST, users.ROLE_ADMIN)
def artist_delete_album(request, album_id):
    if request.method != 'POST':
        return redirect('artist_studio')

    album = uploads.find_own_album(album_id, request.user.id)
    if not album:
        raise Http404('No such album')

    for track in uploads.tracks_for_user(request.user.id):
        if track.album_id == album_id:
            _delete_audio_file(track.audio_file)

    uploads.delete_own_album(album_id, request.user.id)
    messages.success(request, f'Deleted the album "{album.title}" and its tracks.')
    return redirect('artist_studio')


@role_required(users.ROLE_ADMIN)
def admin_approvals(request):
    status = request.GET.get('status', uploads.PENDING)
    if status not in (uploads.PENDING, uploads.APPROVED, uploads.REJECTED):
        status = uploads.PENDING

    context = {
        'submissions': uploads.review_queue(status),
        'status': status,
        'pending_total': uploads.pending_count(),
    }
    return render(request, 'music/admin_approvals.html', context)


@role_required(users.ROLE_ADMIN)
def admin_review_track(request, track_id):
    if request.method != 'POST':
        return redirect('admin_approvals')

    decision = request.POST.get('decision')
    note = (request.POST.get('note') or '').strip()

    if decision not in (uploads.APPROVED, uploads.REJECTED):
        messages.error(request, 'Unknown decision.')
        return redirect('admin_approvals')

    track = db_core.query_one('SELECT id, title FROM music_track WHERE id = %s',
                              [track_id])
    if not track:
        raise Http404('No such track')

    uploads.set_review(track_id, decision, request.user.id, note)
    messages.success(request, f'"{track.title}" {decision}.')
    return redirect('admin_approvals')
