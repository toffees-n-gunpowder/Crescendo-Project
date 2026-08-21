"""
Turn raw upload slugs into readable track titles.

Some Jamendo labels upload files named after their internal asset IDs, so the
track title arrives as e.g.

    onclassical_tamponi_vivaldi_flute_sonata_56_pastor_fido_4

which renders as "onclassical_ta..." in a card. This rewrites those into

    Vivaldi: Flute Sonata 56 Pastor Fido - Mvt. 4

by stripping the label prefix, promoting a recognised composer to the front,
and turning a trailing number into a movement marker.

    python manage.py clean_titles --dry-run
    python manage.py clean_titles
"""

import re

from django.core.management.base import BaseCommand

from music.models import Track
from music.services import composers
from music.services.console import safe

# Label prefixes that are asset-namespacing, not part of the title.
LABEL_PREFIXES = ('onclassical', 'oc', 'jamendo')

ROMAN = {1: 'I', 2: 'II', 3: 'III', 4: 'IV', 5: 'V', 6: 'VI', 7: 'VII', 8: 'VIII'}

# Words that should stay lowercase inside a title.
MINOR_WORDS = {'in', 'of', 'the', 'and', 'for', 'on', 'a', 'an', 'no', 'op'}

# A slug: lowercase letters, digits, underscores and hyphens - and it must
# contain at least one underscore. Requiring the underscore is what stops this
# from rewriting legitimately hyphenated titles like "hip-hop" or "re-entry".
SLUG_RE = re.compile(r'^(?=[^_]*_)[a-z0-9]+([_-][a-z0-9]+)+$')


def _surname_of(canonical):
    return canonical.split()[-1].lower()


# surname -> canonical composer name, for promoting a composer to the front
SURNAMES = {
    _surname_of(name): name
    for name in composers.COMPOSER_REGISTRY
}
# include the aliases too ("dvorak", "rachmaninov", ...)
for _canonical, (_period, _aliases) in composers.COMPOSER_REGISTRY.items():
    for _alias in _aliases:
        if _alias.isalpha():
            SURNAMES.setdefault(_alias, _canonical)


def prettify(slug):
    """Rewrite one slug into a readable title, or return None to leave it alone."""
    if not SLUG_RE.match(slug):
        return None

    parts = re.split(r'[_-]', slug)

    # Drop the label namespace.
    while parts and parts[0] in LABEL_PREFIXES:
        parts.pop(0)
    if not parts:
        return None

    # A trailing bare number is a movement / part index.
    movement = None
    while len(parts) > 1 and parts[-1].isdigit() and len(parts[-1]) <= 2:
        movement = int(parts[-1])
        parts.pop()
        break

    # Slugs follow "<label>_<performer>_<composer>_<work...>", so once a
    # composer is found, everything before it is the performer's name - which
    # is already credited on the track and only clutters the title.
    composer = None
    for i, part in enumerate(parts):
        if part in SURNAMES:
            composer = SURNAMES[part].split()[-1]
            parts = parts[i + 1:]
            break

    if not parts:
        return None

    words = []
    for part in parts:
        if part.isdigit():
            words.append(part)
        elif part in MINOR_WORDS and words:
            words.append(part)
        else:
            words.append(part.capitalize())

    title = ' '.join(words)
    if composer:
        title = f'{composer}: {title}'
    if movement:
        title = f'{title} - Mvt. {ROMAN.get(movement, movement)}'
    return title


class Command(BaseCommand):
    help = 'Rewrites raw slug track titles into readable ones.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Show the rewrites without saving.')

    def handle(self, *args, **options):
        changed = 0
        scanned = 0

        for track in Track.objects.only('id', 'title').iterator(chunk_size=200):
            scanned += 1
            new_title = prettify(track.title)
            if not new_title or new_title == track.title:
                continue

            changed += 1
            self.stdout.write(safe(f'  {track.title[:52]}'))
            self.stdout.write(safe(f'    -> {new_title}'))

            if not options['dry_run']:
                track.title = new_title
                track.save(update_fields=['title'])

        self.stdout.write('')
        self.stdout.write(f'Scanned {scanned} tracks.')
        if options['dry_run']:
            self.stdout.write(self.style.WARNING(f'Dry run - would rewrite {changed} titles.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Rewrote {changed} titles.'))
