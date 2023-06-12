from flask import Flask, request
from flask.sessions import SecureCookieSessionInterface, SessionMixin


class CustomSessionInterface(SecureCookieSessionInterface):
    def should_set_cookie(self, app: "Flask", session: SessionMixin) -> bool:
        path: str = request.path
        if path.startswith('/api/'): return False
        if path.startswith('/static/'): return False
        if path == '/favicon.ico': return False
        return True