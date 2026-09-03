from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .auth.decorators import login_required
from .db import artists as artist_db


def artist_detail(request, artist_id):
    artist = artist_db.get(artist_id)
    if not artist:
        raise Http404('No such artist')

    viewer_id = request.user.id if request.user.is_authenticated else None

    context = {
        'artist': artist,
        'stats': artist_db.stats(artist_id),
        'roles': artist_db.roles_played(artist_id),
        'genres': artist_db.genres(artist_id),
        'albums': artist_db.albums(artist_id),
        'tracks': artist_db.tracks(artist_id),
        'is_following': artist_db.is_following(viewer_id, artist_id),
    }
    return render(request, 'music/artist_detail.html', context)


@login_required
def toggle_follow(request, artist_id):
    if request.method != 'POST':
        return redirect('artist_detail', artist_id=artist_id)

    if not artist_db.get(artist_id):
        raise Http404('No such artist')

    following = artist_db.toggle_follow(request.user.id, artist_id)

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'ok': True,
            'following': following,
            'follower_count': artist_db.stats(artist_id).follower_count,
        })

    return redirect('artist_detail', artist_id=artist_id)
