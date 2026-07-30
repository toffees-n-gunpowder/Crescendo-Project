from django.shortcuts import render
from .models import Track

def home(request):
    # select_related is for ForeignKeys (album, genre, era)
    # prefetch_related is for ManyToManyFields (artists)
    tracks = Track.objects.select_related('album', 'genre', 'era').prefetch_related('artists').all()
    
    context = {
        'tracks': tracks
    }
    return render(request, 'music/home.html', context)