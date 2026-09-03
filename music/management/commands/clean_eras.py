import re

from django.core.management.base import BaseCommand

from music.db import catalog

DECADE_ERA_RE = re.compile(r'^\s*\d{4}\s*s\s*$', re.IGNORECASE)


class Command(BaseCommand):
    help = 'Removes decade-style rows from Era, leaving only musical periods.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Report without deleting.')

    def handle(self, *args, **options):
        eras = catalog.era_counts()

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

        catalog.delete_eras([e.id for e in decades])
        self.stdout.write(self.style.SUCCESS(
            f'\nDeleted {len(decades)} decade rows; {affected} tracks had their era cleared.'
        ))
        self.stdout.write(
            f"{catalog.count('music_era')} musical periods remain. "
            'Release decade is filtered from album.release_date.'
        )
