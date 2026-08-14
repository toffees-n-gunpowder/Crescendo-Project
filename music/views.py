from django.shortcuts import render
from django.shortcuts import render, redirect
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import login, logout
from django.core.paginator import Paginator
from django.db.models import Q
from .models import Track

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Track, LikedTrack, Playlist, PlaylistTrack

#custom user model
from django.contrib.auth.forms import AuthenticationForm
from .forms import CustomUserCreationForm

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Track, LikedTrack  # Make sure LikedTrack is imported!

def home(request):
    # 1. Fetch all tracks
    track_list = Track.objects.prefetch_related('artists').all()
    
    # NEW: 2. Check if a genre button was clicked
    genre_query = request.GET.get('genre')
    if genre_query:
        # Filter tracks where the connected genre's name exactly matches the button
        track_list = track_list.filter(genre__name__iexact=genre_query)
        
    # 2. Search logic
    query = request.GET.get('q')
    if query:
        from django.db.models import Q
        track_list = track_list.filter(
            Q(title__icontains=query) |            
            Q(artists__name__icontains=query) |    
            Q(genre__name__icontains=query)        
        ).distinct() 
        
    # 3. GET LIKED TRACKS AND PLAYLISTS FOR LOGGED IN USER
    liked_track_ids = []
    user_playlists = [] # NEW: Empty list for guests
    
    if request.user.is_authenticated:
        liked_track_ids = LikedTrack.objects.filter(user=request.user).values_list('track_id', flat=True)
        user_playlists = Playlist.objects.filter(user=request.user) # NEW: Get playlists
        
    # 4. Pagination logic
    from django.core.paginator import Paginator
    paginator = Paginator(track_list, 10) 
    page_number = request.GET.get('page')
    tracks = paginator.get_page(page_number)
    
    context = {
        'tracks': tracks,
        'liked_track_ids': liked_track_ids, 
        'user_playlists': user_playlists, # NEW: Send playlists to HTML
    }
    return render(request, 'music/home.html', context)

def register_user(request):
    if request.method == 'POST':
        # Use YOUR custom form here
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('home')
    else:
        # And use YOUR custom form here
        form = CustomUserCreationForm()
        
    return render(request, 'registration/register.html', {'form': form})

def login_user(request):
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user() # Check if password matches
            login(request, user)   # Start the secure session
            return redirect('home')
    else:
        form = AuthenticationForm()
        
    return render(request, 'registration/login.html', {'form': form})
def logout_user(request):
    logout(request) # Destroy the secure session
    return redirect('home')

@login_required(login_url='login')
def toggle_like(request, track_id):
    if request.method == 'POST':
        track = get_object_or_404(Track, id=track_id)
        
        # Check if this user already liked this specific track
        liked_track = LikedTrack.objects.filter(user=request.user, track=track).first()
        
        if liked_track:
            # If it exists, they are "un-liking" it. Delete the record.
            liked_track.delete()
        else:
            # If it doesn't exist, they are "liking" it. Create the record.
            LikedTrack.objects.create(user=request.user, track=track)
            
    # This clever trick sends the user right back to the exact page they were on 
    # (so if they are on Page 2, they don't get kicked back to Page 1)
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
    if request.method == 'POST':
        # 1. Ensure this playlist belongs to the logged-in user
        playlist = get_object_or_404(Playlist, id=playlist_id, user=request.user)
        track = get_object_or_404(Track, id=track_id)
        
        # 2. Find the specific record linking this track to this playlist and delete it
        PlaylistTrack.objects.filter(playlist=playlist, track=track).delete()
            
    # Redirect back to the same playlist page
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
    if request.method == 'POST':
        playlist = get_object_or_404(Playlist, id=playlist_id, user=request.user)
        new_name = request.POST.get('name')
        
        # If they typed a name, update it and save to the database
        if new_name:
            playlist.name = new_name
            playlist.save()
            
    # Send them right back to the playlist they were just looking at
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