from django.core.management.base import BaseCommand, CommandError

from music.auth import users


class Command(BaseCommand):
    help = 'Creates a new admin account, or promotes an existing user to admin.'

    def add_arguments(self, parser):
        parser.add_argument('--username', help='Username for a new admin account.')
        parser.add_argument('--password', help='Password for the new admin account.')
        parser.add_argument('--email', default='', help='Optional email address.')
        parser.add_argument('--promote', help='Promote this existing username to admin.')
        parser.add_argument('--list', action='store_true',
                            help='Show current accounts and their roles.')

    def handle(self, *args, **options):
        if options['list']:
            return self._list()

        if options['promote']:
            return self._promote(options['promote'])

        if options['username'] and options['password']:
            return self._create(options['username'], options['password'],
                                options['email'])

        raise CommandError(
            'Give either --promote <username>, or --username with --password. '
            'Use --list to see existing accounts.'
        )


    def _create(self, username, password, email):
        if users.username_exists(username):
            raise CommandError(
                f'"{username}" already exists. Use --promote {username} instead.'
            )
        if len(password) < 8:
            raise CommandError('Password must be at least 8 characters.')

        user = users.create_user(username, password, email=email,
                                 account_type=users.ROLE_LISTENER)
        users.promote_to_admin(user.id)

        self.stdout.write(self.style.SUCCESS(
            f'Created admin "{username}" (id {user.id}).'
        ))
        self.stdout.write('Password stored as a salted scrypt hash.')

    def _promote(self, username):
        user = users.get_by_username(username)
        if not user:
            raise CommandError(f'No account named "{username}".')

        if user.is_staff or user.is_superuser:
            self.stdout.write(f'"{username}" is already an admin.')
            return

        users.promote_to_admin(user.id)
        self.stdout.write(self.style.SUCCESS(f'Promoted "{username}" to admin.'))

    def _list(self):
        self.stdout.write(f"{'username':22} {'role':10} {'active':7}")
        self.stdout.write('-' * 42)
        for row in users.list_users():
            role = 'admin' if (row.is_staff or row.is_superuser) else row.account_type
            self.stdout.write(f'{row.username:22} {role:10} {str(row.is_active):7}')

        counts = {r.role: r.count for r in users.role_counts()}
        self.stdout.write('')
        self.stdout.write('  '.join(f'{k}: {v}' for k, v in counts.items()) or '(none)')
