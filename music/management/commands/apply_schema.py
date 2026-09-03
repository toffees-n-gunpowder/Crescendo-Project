from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection

SCHEMA_DIR = Path(settings.BASE_DIR) / 'docs' / 'schema'


class Command(BaseCommand):
    help = 'Applies the SQL DDL scripts in docs/schema/ in order.'

    def add_arguments(self, parser):
        parser.add_argument('--list', action='store_true',
                            help='Show the scripts without running them.')

    def handle(self, *args, **options):
        if not SCHEMA_DIR.exists():
            self.stdout.write(self.style.ERROR(f'No schema directory at {SCHEMA_DIR}'))
            return

        scripts = sorted(SCHEMA_DIR.glob('*.sql'))
        if not scripts:
            self.stdout.write('No .sql scripts found.')
            return

        if options['list']:
            self.stdout.write(f'{len(scripts)} script(s) in {SCHEMA_DIR}:')
            for script in scripts:
                self.stdout.write(f'  {script.name}')
            return

        for script in scripts:
            self.stdout.write(f'Applying {script.name}...')
            sql = script.read_text(encoding='utf-8')
            with connection.cursor() as cursor:
                cursor.execute(sql)
            self.stdout.write(self.style.SUCCESS(f'  {script.name} applied.'))

        self.stdout.write(self.style.SUCCESS(f'\n{len(scripts)} script(s) applied.'))
