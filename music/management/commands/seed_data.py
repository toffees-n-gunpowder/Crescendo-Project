import datetime
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from music.models import (
    Artist, Album, Genre, Era, Track, Playlist, PlaylistTrack,
    PersonalGroup, GroupTrack, GroupPlaylist, GroupReview, LikedTrack, PlayHistory
)

User = get_user_model()


class Command(BaseCommand):
    help = "Seeds the Crescendo database with initial test data including Eras, Genres, Artists, Albums, Tracks, and Groups."

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS("Starting Crescendo Database Seeding Process..."))

        # 1. Create Eras
        eras_data = [
            ("1950s", "The birth of Rock 'n' Roll, Bebop Jazz, and early electronic music experiments."),
            ("1960s", "Psychedelic Rock, Motown, Folk Revival, and British Invasion."),
            ("1970s", "Disco, Hard Rock, Funk, Progressive Rock, and early Punk."),
            ("1980s", "Synthwave, New Wave, Hair Metal, and early Hip-Hop."),
            ("Baroque", "Western classical era approx 1600-1750, characterized by counterpoint and ornate ornamentation."),
            ("Romantic", "19th-century classical music featuring intense emotion and dramatic expression."),
            ("Modern Era", "Contemporary 21st-century music across pop, indie, and electronic genres."),
        ]
        eras = {}
        for name, desc in eras_data:
            era, created = Era.objects.get_or_create(name=name, defaults={'description': desc})
            eras[name] = era
            status = "Created" if created else "Found"
            self.stdout.write(f"  [Era] {status}: {name}")

        # 2. Create Genres
        genres_data = ["Classical", "Pop", "Rock", "Synthwave", "Jazz", "Folk", "R&B"]
        genres = {}
        for g_name in genres_data:
            genre, created = Genre.objects.get_or_create(name=g_name)
            genres[g_name] = genre
            status = "Created" if created else "Found"
            self.stdout.write(f"  [Genre] {status}: {g_name}")

        # 3. Create Users
        listener_user, _ = User.objects.get_or_create(
            username="listener_alex",
            defaults={
                "email": "alex@crescendo.com",
                "account_type": "listener",
                "subscription_type": "premium"
            }
        )
        listener_user.set_password("password123")
        listener_user.save()

        artist_user, _ = User.objects.get_or_create(
            username="artist_luna",
            defaults={
                "email": "luna@crescendo.com",
                "account_type": "artist",
                "subscription_type": "premium"
            }
        )
        artist_user.set_password("password123")
        artist_user.save()

        self.stdout.write(self.style.SUCCESS("  [Users] Users seeded: listener_alex, artist_luna."))

        # 4. Create Artists
        artist1, _ = Artist.objects.get_or_create(
            name="Luna & The Echoes",
            defaults={"bio": "Indie synthwave quartet exploring retro 80s landscapes.", "verified": True, "user": artist_user}
        )
        artist2, _ = Artist.objects.get_or_create(
            name="Johann Sebastian Bach",
            defaults={"bio": "German composer and musician of the Baroque period.", "verified": True}
        )
        artist3, _ = Artist.objects.get_or_create(
            name="The Cosmic Velvet",
            defaults={"bio": "70s style psychedelic rock band.", "verified": False}
        )

        # 5. Create Albums & Tracks
        # Album 1
        album1, _ = Album.objects.get_or_create(
            title="Neon Horizon",
            artist=artist1,
            defaults={
                "release_date": datetime.date(2023, 5, 14),
                "cover_url": "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=400&q=80"
            }
        )
        t1, _ = Track.objects.get_or_create(
            album=album1, title="Midnight Drive",
            defaults={"genre": genres["Synthwave"], "era": eras["1980s"], "duration_sec": 245, "track_number": 1}
        )
        t2, _ = Track.objects.get_or_create(
            album=album1, title="Electric Romance",
            defaults={"genre": genres["Synthwave"], "era": eras["1980s"], "duration_sec": 210, "track_number": 2}
        )

        # Album 2
        album2, _ = Album.objects.get_or_create(
            title="Brandenburg Masterpieces",
            artist=artist2,
            defaults={
                "release_date": datetime.date(1721, 3, 24),
                "cover_url": "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?auto=format&fit=crop&w=400&q=80"
            }
        )
        t3, _ = Track.objects.get_or_create(
            album=album2, title="Concerto No. 3 in G Major",
            defaults={"genre": genres["Classical"], "era": eras["Baroque"], "duration_sec": 680, "track_number": 1}
        )

        # Album 3
        album3, _ = Album.objects.get_or_create(
            title="Summer of '69 Memories",
            artist=artist3,
            defaults={
                "release_date": datetime.date(1974, 8, 12),
                "cover_url": "https://images.unsplash.com/photo-1470225620780-dba8ba36b745?auto=format&fit=crop&w=400&q=80"
            }
        )
        t4, _ = Track.objects.get_or_create(
            album=album3, title="Velvet Sunshine",
            defaults={"genre": genres["Rock"], "era": eras["1960s"], "duration_sec": 315, "track_number": 1}
        )

        self.stdout.write(self.style.SUCCESS("  [Albums & Tracks] Seeded tracks linked to Eras & Genres."))

        # 6. Create Playlists & Playlist Tracks
        playlist1, _ = Playlist.objects.get_or_create(
            name="Retro Synth Favorites",
            user=listener_user,
            defaults={"is_public": True}
        )
        PlaylistTrack.objects.get_or_create(playlist=playlist1, track=t1, defaults={"position": 1})
        PlaylistTrack.objects.get_or_create(playlist=playlist1, track=t2, defaults={"position": 2})

        # 7. Create Personal Group, Group Tracks, Group Playlists & Reviews
        group1, _ = PersonalGroup.objects.get_or_create(
            name="Time Travel Audio Journey",
            owner=listener_user,
            defaults={"description": "A curated mixture spanning 1960s rock, 80s synth, and Baroque masterpieces.", "is_public": True}
        )
        GroupTrack.objects.get_or_create(personal_group=group1, track=t1)
        GroupTrack.objects.get_or_create(personal_group=group1, track=t3)
        GroupPlaylist.objects.get_or_create(personal_group=group1, playlist=playlist1)

        GroupReview.objects.get_or_create(
            group=group1,
            reviewer=artist_user,
            defaults={"rating": 5, "review_text": "Incredible blend of historical eras and modern synthwave!"}
        )

        # 8. Seed PlayHistory & LikedTrack
        LikedTrack.objects.get_or_create(user=listener_user, track=t1)
        PlayHistory.objects.create(user=listener_user, track=t1)

        self.stdout.write(self.style.SUCCESS("Successfully completed Crescendo database seeding!"))
