import re

from django.core.management.base import BaseCommand

from music.db import catalog
from music.services import composers
from music.services.console import safe

LABEL_PREFIXES = ('onclassical', 'oc', 'jamendo')

ROMAN = {1: 'I', 2: 'II', 3: 'III', 4: 'IV', 5: 'V', 6: 'VI', 7: 'VII', 8: 'VIII'}

MINOR_WORDS = {'in', 'of', 'the', 'and', 'for', 'on', 'a', 'an', 'no', 'op'}

SLUG_RE = re.compile(r'^(?=[^_]*_)[a-z0-9]+([_-][a-z0-9]+)+$')


def _surname_of(canonical):
    return canonical.split()[-1].lower()


SURNAMES = {
    _surname_of(name): name
    for name in composers.COMPOSER_REGISTRY
}
for _canonical, (_period, _aliases) in composers.COMPOSER_REGISTRY.items():
    for _alias in _aliases:
        if _alias.isalpha():
            SURNAMES.setdefault(_alias, _canonical)


def prettify(slug):
    if not SLUG_RE.match(slug):
        return None

    parts = re.split(r'[_-]', slug)

    while parts and parts[0] in LABEL_PREFIXES:
        parts.pop(0)
    if not parts:
        return None

    movement = None
    while len(parts) > 1 and parts[-1].isdigit() and len(parts[-1]) <= 2:
        movement = int(parts[-1])
        parts.pop()
        break

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

        for track in catalog.track_titles():
            scanned += 1
            new_title = prettify(track.title)
            if not new_title or new_title == track.title:
                continue

            changed += 1
            self.stdout.write(safe(f'  {track.title[:52]}'))
            self.stdout.write(safe(f'    -> {new_title}'))

            if not options['dry_run']:
                catalog.set_track_title(track.id, new_title)

        self.stdout.write('')
        self.stdout.write(f'Scanned {scanned} tracks.')
        if options['dry_run']:
            self.stdout.write(self.style.WARNING(f'Dry run - would rewrite {changed} titles.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Rewrote {changed} titles.'))
