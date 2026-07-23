"""
Punto de entrada de la aplicación.
  - Desarrollo: flask run (usa la variable FLASK_APP=wsgi.py)
  - Producción: gunicorn wsgi:app

SOCKET-17 (Auditoría Día 39): antes este archivo arrancaba con
socketio.run(). Se eliminó junto con Flask-SocketIO, que era código
muerto (ver la nota en app/extensions.py). Ahora usa app.run() normal.

Nota: el Dockerfile de producción ya arrancaba con
'gunicorn --bind 0.0.0.0:5000 wsgi:app', SIN '-k eventlet', así que
Socket.IO tampoco habría funcionado ahí. El docstring anterior decía
'gunicorn -k eventlet' pero no correspondía a la realidad del Dockerfile.
"""
from app import create_app

app = create_app()

if __name__ == "__main__":
    import os
    # debug=False por defecto. El debugger interactivo de Werkzeug permite RCE
    # si se activa en un entorno accesible. En desarrollo, docker-compose ya usa
    # 'flask run --debug'; este bloque solo corre con 'python wsgi.py'.
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=5000, debug=debug)
