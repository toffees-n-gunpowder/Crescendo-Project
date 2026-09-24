from django.contrib import messages
from django.db import DatabaseError
from django.shortcuts import render, redirect
from django.http import Http404, JsonResponse
from music.auth.decorators import login_required
from music.db import social as social_db
from music.db import artists as artist_db

@login_required
def history(request):
    played_tracks = social_db.get_play_history(request.user.id)
    return render(request, 'music/history.html', {'tracks': played_tracks})

@login_required
def follows(request):
    artists = social_db.get_followed_artists(request.user.id)
    return render(request, 'music/follows.html', {'artists': artists})

@login_required
def toggle_follow(request, artist_id):
    if request.method == 'POST':
        if not artist_db.get(artist_id):
            raise Http404('No such artist')

        is_following = artist_db.toggle_follow(request.user.id, artist_id)

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'following': is_following, 'artist_id': artist_id})
    return redirect('follows')

@login_required
def record_play(request, track_id):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'detail': 'POST required.'}, status=405)

    if not social_db.track_is_addable(track_id):
        return JsonResponse({'status': 'error', 'detail': 'No such track.'}, status=404)

    recorded = social_db.record_play_once(request.user.id, track_id)
    return JsonResponse({'status': 'ok', 'recorded': bool(recorded)})

def _as_id(raw):
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


@login_required
def groups(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        desc = request.POST.get('description', '').strip()
        is_public = request.POST.get('is_public') == 'on'
        if name:
            social_db.create_group(request.user.id, name, desc, is_public=is_public)
            return redirect('groups')
            
    search_query = request.GET.get('q', '').strip()
    all_groups = social_db.list_groups(request.user.id, search_query=search_query)
    
    my_groups = [g for g in all_groups if g['owner_id'] == request.user.id]
    global_groups = [g for g in all_groups if g['owner_id'] != request.user.id and g['is_public']]
    
    context = {
        'my_groups': my_groups,
        'global_groups': global_groups,
        'search_query': search_query
    }
    return render(request, 'music/groups.html', context)

@login_required
def group_detail(request, group_id):
    group = social_db.get_group(group_id)
    if not group:
        raise Http404("Group not found")
        
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'review':
            rating = int(request.POST.get('rating', 0))
            text = request.POST.get('review_text', '').strip()
            if rating >= 1 and rating <= 5:
                try:
                    social_db.add_group_review(group_id, request.user.id, rating, text)
                except DatabaseError as e:
                    messages.error(request, str(e))
        elif action == 'add_track':
            if request.user.id != group.owner_id:
                messages.error(request, "Only the group owner can add tracks.")
            else:
                track_id = _as_id(request.POST.get('track_id'))
                if not track_id:
                    messages.error(request, "Pick a track from the list.")
                elif not social_db.track_is_addable(track_id):
                    messages.error(request, "That track is not available.")
                elif social_db.add_group_track(group_id, track_id):
                    messages.success(request, "Track added to the group.")
                else:
                    messages.info(request, "That track is already in this group.")
        elif action == 'add_playlist':
            if request.user.id != group.owner_id:
                messages.error(request, "Only the group owner can add playlists.")
            else:
                playlist_id = _as_id(request.POST.get('playlist_id'))
                if not playlist_id:
                    messages.error(request, "Pick a playlist from the list.")
                elif not social_db.playlist_is_addable(playlist_id, request.user.id):
                    messages.error(
                        request,
                        "You can only add your own playlists or someone else's public ones.",
                    )
                elif social_db.add_group_playlist(group_id, playlist_id):
                    messages.success(request, "Playlist added to the group.")
                else:
                    messages.info(request, "That playlist is already in this group.")
        elif action == 'remove_track':
            if request.user.id != group.owner_id:
                messages.error(request, "Only the group owner can remove tracks.")
            else:
                track_id = _as_id(request.POST.get('track_id'))
                if track_id and social_db.remove_group_track(group_id, track_id):
                    messages.success(request, "Track removed from the group.")
                else:
                    messages.error(request, "That track is not in this group.")
        elif action == 'remove_playlist':
            if request.user.id != group.owner_id:
                messages.error(request, "Only the group owner can remove playlists.")
            else:
                playlist_id = _as_id(request.POST.get('playlist_id'))
                if playlist_id and social_db.remove_group_playlist(group_id, playlist_id):
                    messages.success(request, "Playlist removed from the group.")
                else:
                    messages.error(request, "That playlist is not in this group.")
        elif action == 'delete_review':
            review_id = _as_id(request.POST.get('review_id'))
            if review_id and social_db.delete_own_review(review_id, request.user.id):
                messages.success(request, "Your review was deleted.")
            else:
                messages.error(request, "You can only delete your own review.")
        elif action == 'delete_group':
            try:
                if social_db.delete_group(group_id, request.user.id):
                    messages.success(request, f'Group "{group.name}" deleted.')
                    return redirect('groups')
                messages.error(request, "Only the group owner can delete the group.")
            except DatabaseError as e:
                messages.error(request, str(e))
        elif action == 'edit_visibility':
            if request.user.id == group.owner_id:
                is_public = request.POST.get('is_public') == 'on'
                social_db.update_group_visibility(group_id, is_public)
            else:
                messages.error(request, "Only the group owner can change visibility.")
        return redirect('group_detail', group_id=group_id)

    tracks = social_db.group_tracks(group_id)
    reviews = social_db.group_reviews(group_id)
    playlists = social_db.group_playlists(group_id)

    is_owner = request.user.id == group.owner_id

    return render(request, 'music/group_detail.html', {
        'group': group,
        'tracks': tracks,
        'reviews': reviews,
        'playlists': playlists,
        'is_owner': is_owner,
        'addable_tracks': social_db.addable_tracks(group_id) if is_owner else [],
        'addable_playlists': (social_db.addable_playlists(request.user.id, group_id)
                              if is_owner else []),
    })
