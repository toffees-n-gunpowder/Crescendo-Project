from django.shortcuts import render
from .models import Track

def home(request):
    all_tracks = Track.objects.select_related('album__artist').all()
    
    context = {
        'tracks': all_tracks
    }
    return render(request, 'music/home.html', context)