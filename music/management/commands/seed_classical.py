"""
Seed the classical repertoire - Mozart, Beethoven, Prokofiev and friends.

Jamendo carries Creative Commons *recordings* of public-domain works, so we
search per composer and file everything under the Classical genre, tagged with
the composer's historical period (Baroque / Classical Era / Romantic / Modern)
rather than the recording's release decade.

    python manage.py seed_classical                       # all composers below
    python manage.py seed_classical --per-composer 40     # deeper per composer
    python manage.py seed_classical --composer "Erik Satie" --period Romantic
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from music.models import Genre, Track
from music.services import composers, jamendo
from music.services.console import safe

CLASSICAL_GENRE = 'Classical'

# (search term, historical period). The period becomes the track's Era, which
# powers the "Baroque / Romantic" filters on the search page.
COMPOSERS = [
    ('Vivaldi', 'Baroque'),
    ('Bach', 'Baroque'),
    ('Handel', 'Baroque'),
    ('Mozart', 'Classical Era'),
    ('Haydn', 'Classical Era'),
    ('Beethoven', 'Classical Era'),
    ('Schubert', 'Romantic'),
    ('Chopin', 'Romantic'),
    ('Liszt', 'Romantic'),
    ('Brahms', 'Romantic'),
    ('Tchaikovsky', 'Romantic'),
    ('Grieg', 'Romantic'),
    ('Dvorak', 'Romantic'),
    ('Debussy', 'Impressionist'),
    ('Ravel', 'Impressionist'),
    ('Satie', 'Impressionist'),
    ('Prokofiev', 'Modern'),
    ('Shostakovich', 'Modern'),
    ('Stravinsky', 'Modern'),
    ('Rachmaninoff', 'Modern'),
]

PERIOD_DESCRIPTIONS = {
    'Baroque': 'Ornate counterpoint and basso continuo, roughly 1600-1750.',
    'Classical Era': 'Balance, clarity and sonata form, roughly 1750-1820.',
    'Romantic': 'Expressive, expansive and nationalistic, roughly 1820-1900.',
    'Impressionist': 'Colour, mood and blurred tonality, roughly 1875-1925.',
    'Modern': 'Twentieth-century dissonance, rhythm and reinvention.',
}


class Command(BaseCommand):
    help = 'Seeds classical recordings (Mozart, Beethoven, Prokofiev, ...) from Jamendo.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--per-composer', type=int, default=20,
            help='How many tracks to pull per composer. Default 20.',
        )
        parser.add_argument(
            '--composer', type=str, default='',
            help='Seed a single composer instead of the full list.',
        )
        parser.add_argument(
            '--period', type=str, default='Modern',
            help='Historical period to file --composer under. Default Modern.',
        )

    def handle(self, *args, **options):
        if options['composer']:
            targets = [(options['composer'], options['period'])]
        else:
            targets = COMPOSERS

        # Make sure the genre and every period exist even if a search comes back
        # empty, so the browse filters render consistently.
        Genre.objects.get_or_create(name=CLASSICAL_GENRE)

        total_new = 0
        total_seen = 0

        for composer, period in targets:
            self.stdout.write(f'\nSearching Jamendo for {composer} ({period})...')
            try:
                items = jamendo.fetch_tracks(
                    limit=options['per_composer'],
                    search=composer,
                    order='popularity_total',
                )
                new, seen = self._import(items, composer, period)
            except jamendo.JamendoError as exc:
                raise CommandError(str(exc))

            total_new += new
            total_seen += seen
            if seen == 0:
                self.stdout.write(self.style.WARNING(f'  no recordings found for {composer}'))
            else:
                self.stdout.write(f'  {composer}: {seen} returned, {new} new.')

        classical_total = Track.objects.filter(genre__name=CLASSICAL_GENRE).count()
        self.stdout.write(self.style.SUCCESS(
            f'\nDone. {total_seen} recordings returned, {total_new} newly added.'
        ))
        self.stdout.write(f'The Classical genre now holds {classical_total} tracks.')

    def _import(self, items, composer, period):
        new = 0
        seen = 0
        for item in items:
            seen += 1
            try:
                with transaction.atomic():
                    track, created = jamendo.import_track(
                        item,
                        genre_override=CLASSICAL_GENRE,
                        era_override=period,
                    )
                    self._describe_period(period)
                    # Jamendo credits the performer, not the composer - add the
                    # composer as a writer so artist searches can find them.
                    composers.credit_detected(track)
            except Exception as exc:
                self.stderr.write(safe(f'  skipped "{item.get("name", "?")}": {exc}'))
                continue
            if created:
                new += 1
                self.stdout.write(safe(f'  + {track.title} - {item.get("artist_name", "?")}'))
        return new, seen

    def _describe_period(self, period):
        """Give freshly created Era rows a human description."""
        from music.models import Era

        era = Era.objects.filter(name=period).first()
        if era and not era.description:
            era.description = PERIOD_DESCRIPTIONS.get(period, f'{period} period works.')
            era.save(update_fields=['description'])
