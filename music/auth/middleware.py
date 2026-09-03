from music.auth import sessions, users


class SessionAuthMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        session_key = request.COOKIES.get(sessions.COOKIE_NAME)
        request.session_key = session_key
        request.user = self._resolve(session_key)
        return self.get_response(request)

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
