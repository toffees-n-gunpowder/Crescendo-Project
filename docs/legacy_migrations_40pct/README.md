# Legacy migrations (40% milestone)

These ORM migrations created the `music_*` tables in the live database. They are
kept for reference and for the 40% milestone's history.

They are **no longer runnable**: they import `django.db.models` and
`django.contrib.auth`, both of which were removed when the project moved to raw
SQL. `manage.py migrate` is not used any more.

Schema changes now go in `docs/schema/*.sql` and are applied with:

    python manage.py apply_schema
