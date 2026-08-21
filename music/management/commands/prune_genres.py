"""
Collapse niche genres into their parent family.

Jamendo tags are extremely fine-grained: a catalogue of 649 tracks arrives split
across 39 genres, 27 of which hold fewer than ten tracks ("Smoothjazz" 1,
"Electroswing" 1, "Chillhop" 1). That makes the genre chips useless.

Rather than deleting those genres and leaving their tracks uncategorised, each
one is merged into a broader parent - Smoothjazz into Jazz, Chillhop into
Hip-Hop - and only then removed. Parents resolve transitively, so Soul -> R&B
-> Pop lands on Pop.

    python manage.py prune_genres --dry-run
    python manage.py prune_genres
    python manage.py prune_genres --min 20
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count

from music.models import Genre, Track

# Broad families that are kept as-is - the buckets everything else drains into.
ROOT_GENRES = {
    'Classical', 'Pop', 'Rock', 'Metal', 'Jazz', 'Electronic',
    'Hip-Hop', 'Blues', 'Folk', 'Ambient', 'Chillout', 'Indie',
}

# niche genre -> parent. Resolved transitively, so a chain is fine.
PARENT_GENRE = {
    # soul family
    'R&B': 'Pop',
    'Soul': 'R&B',
    'Funk': 'R&B',
    'Reggae': 'Pop',
    'Corporate': 'Pop',
    # jazz family
    'Jazzfunk': 'Jazz',
    'Nujazz': 'Jazz',
    'Smoothjazz': 'Jazz',
    'Freejazz': 'Jazz',
    'Electroswing': 'Jazz',
    # folk / acoustic family
    'Country': 'Folk',
    'World': 'Folk',
    'Latin': 'Folk',
    'Singersongwriter': 'Folk',
    # hip-hop family
    'Triphop': 'Hip-Hop',
    'Chillhop': 'Hip-Hop',
    # electronic family
    'Electronica': 'Electronic',
    'Trance': 'Electronic',
    'Electrorock': 'Electronic',
    'House': 'Electronic',
    'Techno': 'Electronic',
    'Dubstep': 'Electronic',
    'Drumnbass': 'Electronic',
    # downtempo family
    'Downtempo': 'Chillout',
    'Lounge': 'Chillout',
    'Newage': 'Ambient',
    # rock family
    'Punk': 'Rock',
    'Bluesrock': 'Blues',
    'Hardcore': 'Metal',
    'Grunge': 'Rock',
    'Alternative': 'Rock',
    # orchestral family
    'Filmscore': 'Classical',
    'Trailer': 'Classical',
    'Soundtrack': 'Classical',
    'Orchestral': 'Classical',
    'Contemporarypiano': 'Classical',
    'Opera': 'Classical',
    'Baroque': 'Classical',
}


def resolve_parent(name, seen=None):
    """Follow the parent chain to a root genre. Returns None if there isn't one."""
    seen = seen or set()
    if name in seen:            # guard against a cycle in the map
        return None
    seen.add(name)

    parent = PARENT_GENRE.get(name)
    if not parent:
        return None
    if parent in ROOT_GENRES:
        return parent
    return resolve_parent(parent, seen) or parent


class Command(BaseCommand):
    help = 'Merges genres below a track threshold into their parent family.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--min', type=int, default=10,
            help='Genres with fewer tracks than this are merged away. Default 10.',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report the plan without changing anything.',
        )
        parser.add_argument(
            '--drop-unmapped', action='store_true',
            help='Also delete small genres that have no parent (their tracks lose '
                 'their genre). Off by default - they are reported instead.',
        )

    def handle(self, *args, **options):
        minimum = options['min']
        dry_run = options['dry_run']

        small = [
            g for g in Genre.objects.annotate(c=Count('tracks')).order_by('c')
            if g.c < minimum
        ]
        if not small:
            self.stdout.write(f'Every genre already has {minimum}+ tracks.')
            return

        self.stdout.write(f'{len(small)} genres hold fewer than {minimum} tracks.\n')

        merged = 0
        moved = 0
        unmapped = []

        for genre in small:
            target_name = resolve_parent(genre.name)

            if not target_name:
                unmapped.append(genre)
                continue

            count = Track.objects.filter(genre=genre).count()
            self.stdout.write(f'  {genre.name:22} ({count:3d}) -> {target_name}')

            if dry_run:
                merged += 1
                moved += count
                continue

            with transaction.atomic():
                target, _ = Genre.objects.get_or_create(name=target_name)
                moved += Track.objects.filter(genre=genre).update(genre=target)
                genre.delete()
                merged += 1

        if unmapped:
            self.stdout.write('\nNo parent family defined for:')
            for genre in unmapped:
                count = Track.objects.filter(genre=genre).count()
                self.stdout.write(f'  {genre.name:22} ({count:3d} tracks)')

            if options['drop_unmapped'] and not dry_run:
                for genre in unmapped:
                    genre.delete()
                self.stdout.write(self.style.WARNING(
                    f'Deleted {len(unmapped)} unmapped genres; their tracks now have none.'
                ))
            else:
                self.stdout.write(
                    'Left in place. Add them to PARENT_GENRE, or re-run with '
                    '--drop-unmapped to remove them.'
                )

        self.stdout.write('')
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'Dry run - would merge {merged} genres and move {moved} tracks.'
            ))
            return

        self.stdout.write(self.style.SUCCESS(
            f'Merged {merged} genres, moved {moved} tracks.'
        ))
        self.stdout.write('\nRemaining genres:')
        for g in Genre.objects.annotate(c=Count('tracks')).order_by('-c'):
            self.stdout.write(f'  {g.name:22} {g.c:4d}')
