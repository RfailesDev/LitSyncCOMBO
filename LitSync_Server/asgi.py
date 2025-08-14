# asgi.py
from app import create_app
from socketio import ASGIApp

app, sio, _, _ = create_app()

# asgi_app экспортируется для запуска через Hypercorn
asgi_app = ASGIApp(sio, other_asgi_app=app)