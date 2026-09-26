from music.auth import sessions, users

# The session cookie is shared by every tab, so on its own it can't tell a new
# tab from the one the user logged in with. sessionStorage is per tab: the
# login page marks this tab when the form is submitted, the first page after
# login records the user in it, and a page opened in a tab without that record
# (a pasted URL, a new window) is hidden and sent to the login page.
TAB_KEY = 'crescendo_tab_user'
LOGIN_PENDING_KEY = 'crescendo_login_pending'

LOGIN_PAGE_SCRIPT = """<script>
(function () {
  try {
    sessionStorage.removeItem('__TAB__');
    sessionStorage.removeItem('__PENDING__');
  } catch (e) {}
  document.addEventListener('submit', function () {
    try { sessionStorage.setItem('__PENDING__', '1'); } catch (e) {}
  }, true);
})();
</script>"""

TAB_GUARD_SCRIPT = """<script>
(function () {
  var me = '__USER__';
  try {
    if (sessionStorage.getItem('__PENDING__')) {
      sessionStorage.removeItem('__PENDING__');
      sessionStorage.setItem('__TAB__', me);
    }
    if (sessionStorage.getItem('__TAB__') === me) return;
  } catch (e) { return; }
  document.documentElement.style.visibility = 'hidden';
  location.replace('/login/?next=' + encodeURIComponent(location.pathname + location.search));
})();
</script>"""


def _tab_script(template, user_id=''):
    return (template.replace('__TAB__', TAB_KEY)
                    .replace('__PENDING__', LOGIN_PENDING_KEY)
                    .replace('__USER__', str(user_id)))


class SessionAuthMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        session_key = request.COOKIES.get(sessions.COOKIE_NAME)
        request.session_key = session_key
        request.user = self._resolve(session_key)

        from django.shortcuts import redirect
        from django.conf import settings
        
        path = request.path_info.lower()
        allowed_paths = [
            '/login', '/register', '/admin', 
            settings.STATIC_URL.lower(), settings.MEDIA_URL.lower()
        ]
        
        is_allowed = any(path.startswith(p) for p in allowed_paths)
        if not is_allowed and not request.user.is_authenticated:
            return redirect(f"{settings.LOGIN_URL}?next={request.path}")

        return self._add_tab_guard(request, self.get_response(request))

    def _add_tab_guard(self, request, response):
        if response.streaming or 'text/html' not in response.get('Content-Type', ''):
            return response

        path = request.path_info.lower()
        if path.startswith('/login'):
            script = _tab_script(LOGIN_PAGE_SCRIPT)
        elif request.user.is_authenticated and not path.startswith('/register'):
            script = _tab_script(TAB_GUARD_SCRIPT, request.user.id)
        else:
            return response

        content = response.content.decode(response.charset)
        if '<head>' not in content:
            return response

        response.content = content.replace('<head>', '<head>' + script, 1).encode(response.charset)
        if response.has_header('Content-Length'):
            response['Content-Length'] = str(len(response.content))
        return response

    def _resolve(self, session_key):
        if not session_key:
            return users.AnonymousUser()

        user_id = sessions.get_user_id(session_key)
        if not user_id:
            return users.AnonymousUser()

        row = users.get_by_id(user_id)
        if not row:
            return users.AnonymousUser()

        return users.AuthUser(row)


def auth_context(request):
    user = getattr(request, 'user', None) or users.AnonymousUser()
    return {
        'user': user,
        'is_admin': user.has_role(users.ROLE_ADMIN),
        'is_artist': user.has_role(users.ROLE_ARTIST),
    }
