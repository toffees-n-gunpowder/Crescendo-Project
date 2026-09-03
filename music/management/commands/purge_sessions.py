from django.core.management.base import BaseCommand, CommandError

from music.auth import sessions, users
from music.db import core


class Command(BaseCommand):
    help = 'Deletes expired sessions from app_session.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Report without deleting.')
        parser.add_argument('--user', type=str, default='',
                            help='Instead, end every session for this username.')

    def handle(self, *args, **options):
        if options['user']:
            return self._purge_user(options['user'])

        total = core.scalar('SELECT COUNT(*) FROM app_session') or 0
        expired = core.scalar(
            'SELECT COUNT(*) FROM app_session WHERE expires_at <= NOW()'
        ) or 0

        self.stdout.write(f'{total} session(s) stored; {expired} expired.')

        if options['dry_run']:
            self.stdout.write(self.style.WARNING(
                f'Dry run - would delete {expired} row(s).'
            ))
            return

        deleted = sessions.purge_expired()
        self.stdout.write(self.style.SUCCESS(f'Deleted {deleted} expired session(s).'))
        self.stdout.write(f'{total - deleted} live session(s) remain.')

    def _purge_user(self, username):
        user = users.get_by_username(username)
        if not user:
            raise CommandError(f'No account named "{username}".')

        deleted = sessions.destroy_all_for_user(user.id)
        self.stdout.write(self.style.SUCCESS(
            f'Ended {deleted} session(s) for "{username}" - they are now signed out everywhere.'
        ))
