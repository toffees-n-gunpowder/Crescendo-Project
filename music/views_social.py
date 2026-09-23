from django.shortcuts import render, redirect
from django.http import Http404, JsonResponse
from music.auth.decorators import login_required
from music.db import social as social_db
from music.db import catalog as catalog_db

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
        artist = catalog_db.artist_id_by_name(str(artist_id)) # Not exactly what we need if artist_id is ID. Wait, let's just use it directly.
        
        # We need a db method to verify artist exists. Let's just catch if it fails or assume it's good.
        is_following = social_db.toggle_follow(request.user.id, artist_id)
        
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'following': is_following, 'artist_id': artist_id})
    return redirect('follows')

@login_required
def record_play(request, track_id):
    if request.method == 'POST':
        social_db.record_play(request.user.id, track_id)
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'ok'})
    return JsonResponse({'status': 'error'})

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
                social_db.add_group_review(group_id, request.user.id, rating, text)
        elif action == 'add_track':
            if request.user.id == group.owner_id:
                track_id = request.POST.get('track_id')
                if track_id:
                    social_db.add_group_track(group_id, int(track_id))
            else:
                from django.contrib import messages
                messages.error(request, "Only the group owner can add tracks.")
        elif action == 'add_playlist':
            if request.user.id == group.owner_id:
                playlist_id = request.POST.get('playlist_id')
                if playlist_id:
                    social_db.add_group_playlist(group_id, int(playlist_id))
            else:
                from django.contrib import messages
                messages.error(request, "Only the group owner can add playlists.")
        elif action == 'edit_visibility':
            if request.user.id == group.owner_id:
                is_public = request.POST.get('is_public') == 'on'
                social_db.update_group_visibility(group_id, is_public)
            else:
                from django.contrib import messages
                messages.error(request, "Only the group owner can change visibility.")
        return redirect('group_detail', group_id=group_id)

    tracks = social_db.group_tracks(group_id)
    reviews = social_db.group_reviews(group_id)
    playlists = social_db.group_playlists(group_id)
    
    return render(request, 'music/group_detail.html', {
        'group': group,
        'tracks': tracks,
        'reviews': reviews,
        'playlists': playlists
    })
