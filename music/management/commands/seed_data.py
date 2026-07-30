import requests
from datetime import datetime
from django.core.management.base import BaseCommand
from music.models import Artist, Album, AlbumCredit, Track, TrackCredit, Genre

class Command(BaseCommand):
    help = 'Seeds the database with top tracks from the Jamendo API'

    def handle(self, *args, **kwargs):
        self.stdout.write("Connecting to Jamendo API...")
        
        # ⚠️ REMEMBER: Replace this with your actual Client ID from developer.jamendo.com
        CLIENT_ID = '33ec4882' 
        
        url = f"https://api.jamendo.com/v3.0/tracks/?client_id={CLIENT_ID}&format=json&limit=20&include=musicinfo"
        
        response = requests.get(url)
        if response.status_code != 200:
            self.stdout.write(self.style.ERROR('Failed to connect to API. Check your Client ID.'))
            return
            
        data = response.json()
        
        for item in data.get('results', []):
            # 1. Create or get the Artist
            artist, _ = Artist.objects.get_or_create(
                name=item.get('artist_name', 'Unknown Artist')
            )
            
            # 2. Create or get the Album
            release_date_str = item.get('releasedate')
            release_date = datetime.strptime(release_date_str, '%Y-%m-%d').date() if release_date_str else datetime.now().date()
                
            album, _ = Album.objects.get_or_create(
                title=item.get('album_name', 'Unknown Album'),
                defaults={'release_date': release_date, 'cover_url': item.get('image', '')}
            )
            
            AlbumCredit.objects.get_or_create(album=album, artist=artist, role='primary')
            
            # 3. Create or get the Genre
            tags = item.get('musicinfo', {}).get('tags', {}).get('genres', [])
            genre_name = tags[0] if tags else 'Indie'
            genre, _ = Genre.objects.get_or_create(name=genre_name.capitalize())
            
            # 4. Create the Track
            track, _ = Track.objects.get_or_create(
                title=item.get('name', 'Unknown Track'),
                album=album,
                defaults={
                    'genre': genre,
                    'duration_sec': item.get('duration', 0),
                    'audio_file': item.get('audio', ''),
                }
            )
            
            TrackCredit.objects.get_or_create(track=track, artist=artist, role='primary')
            
            self.stdout.write(self.style.SUCCESS(f"Added: {track.title} by {artist.name}"))

        self.stdout.write(self.style.SUCCESS('Successfully seeded database from Jamendo!'))