"""
Punto de entrada de la aplicación.
  - Desarrollo: flask run (usa la variable FLASK_APP=wsgi.py)
  - Producción: gunicorn -k eventlet -w 1 wsgi:app
"""
from app import create_app
from app.extensions import socketio

app = create_app()

if __name__ == "__main__":
    import os
    # debug=False por defecto. El debugger interactivo de Werkzeug permite RCE
    # si se activa en un entorno accesible. En desarrollo, docker-compose ya usa
    # 'flask run --debug'; este bloque solo corre con 'python wsgi.py'.
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    socketio.run(app, host="0.0.0.0", port=5000, debug=debug)
