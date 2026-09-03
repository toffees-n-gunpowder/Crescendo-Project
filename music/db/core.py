from django.db import connection

NEST = '__'


class Row:

    def __init__(self, data=None):
        self._data = dict(data or {})

    def __getattr__(self, name):
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError(name)

    def __getitem__(self, key):
        return self._data[key]

    def get(self, key, default=None):
        return self._data.get(key, default)

    def __contains__(self, key):
        return key in self._data

    def __setitem__(self, key, value):
        self._data[key] = value

    def keys(self):
        return self._data.keys()

    def items(self):
        return self._data.items()

    def __bool__(self):
        return any(v is not None for v in self._data.values())

    def __repr__(self):
        return f'Row({self._data!r})'


class RelatedList(list):

    @property
    def all(self):
        return self


def _nest(flat):
    top = {}
    children = {}

    for key, value in flat.items():
        if NEST in key:
            child, _, field = key.partition(NEST)
            children.setdefault(child, {})[field] = value
        else:
            top[key] = value

    for name, fields in children.items():
        top[name] = Row(fields) if any(v is not None for v in fields.values()) else None

    return Row(top)


def query(sql, params=None):
    with connection.cursor() as cursor:
        cursor.execute(sql, params or [])
        columns = [col[0] for col in cursor.description]
        return [_nest(dict(zip(columns, record))) for record in cursor.fetchall()]


def query_one(sql, params=None):
    rows = query(sql, params)
    return rows[0] if rows else None


def scalar(sql, params=None):
    with connection.cursor() as cursor:
        cursor.execute(sql, params or [])
        record = cursor.fetchone()
        return record[0] if record else None


def execute(sql, params=None):
    with connection.cursor() as cursor:
        cursor.execute(sql, params or [])
        return cursor.rowcount


def insert_returning_id(sql, params=None):
    return scalar(sql, params)


class Page:

    def __init__(self, rows, number, per_page, total):
        self.object_list = rows
        self.number = max(1, number)
        self.per_page = per_page
        self.count = total
        self.num_pages = max(1, -(-total // per_page))
        self.paginator = self

    def __iter__(self):
        return iter(self.object_list)

    def __len__(self):
        return len(self.object_list)

    def has_previous(self):
        return self.number > 1

    def has_next(self):
        return self.number < self.num_pages

    def has_other_pages(self):
        return self.num_pages > 1

    def previous_page_number(self):
        return self.number - 1

    def next_page_number(self):
        return self.number + 1


def paginate(rows, total, number, per_page):
    return Page(rows, number, per_page, total)


def page_number(raw, num_pages=None):
    try:
        number = int(raw)
    except (TypeError, ValueError):
        return 1
    if number < 1:
        return 1
    if num_pages and number > num_pages:
        return num_pages
    return number
