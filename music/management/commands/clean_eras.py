"""
Separate musical period from release decade.

The Era table was being used for two unrelated things at once:

  * musical periods  - Baroque, Classical Era, Romantic, Impressionist, Modern
  * release decades  - 2000s, 2010s, 2020s

That made the Era dropdown a duplicate of the Decade filter, and mixing them is
meaningless anyway: a 2009 recording of Vivaldi is Baroque music released in the
2000s, and those two facts answer different questions.

Decade is now derived from album.release_date at query time, so the decade rows
in Era are redundant. This deletes them; Track.era is SET_NULL, so the affected
tracks simply lose an era they should never have had.

    python manage.py clean_eras --dry-run
    python manage.py clean_eras
"""

import re

from django.core.management.base import BaseCommand
from django.db.models import Count

from music.models import Era

# "1990s", "2000s", "2020s" - a decade label, not a musical period.
DECADE_ERA_RE = re.compile(r'^\s*\d{4}\s*s\s*$', re.IGNORECASE)


class Command(BaseCommand):
    help = 'Removes decade-style rows from Era, leaving only musical periods.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Report without deleting.')

    def handle(self, *args, **options):
        eras = Era.objects.annotate(track_count=Count('tracks')).order_by('name')

        decades = [e for e in eras if DECADE_ERA_RE.match(e.name)]
        periods = [e for e in eras if not DECADE_ERA_RE.match(e.name)]

        self.stdout.write('Musical periods (kept):')
        for era in periods:
            self.stdout.write(f'  {era.name:20} {era.track_count:4d} tracks')

        if not decades:
            self.stdout.write('\nNo decade rows in Era - nothing to do.')
            return

        self.stdout.write('\nDecade rows (removed - decade now comes from release date):')
        affected = 0
        for era in decades:
            self.stdout.write(f'  {era.name:20} {era.track_count:4d} tracks')
            affected += era.track_count

        if options['dry_run']:
            self.stdout.write(self.style.WARNING(
                f'\nDry run - would delete {len(decades)} era rows '
                f'and clear era on {affected} tracks.'
            ))
            return

        Era.objects.filter(id__in=[e.id for e in decades]).delete()
        self.stdout.write(self.style.SUCCESS(
            f'\nDeleted {len(decades)} decade rows; {affected} tracks had their era cleared.'
        ))
        self.stdout.write(
            f'{Era.objects.count()} musical periods remain. '
            'Release decade is filtered from album.release_date.'
        )
