"""
Punto de entrada de la aplicación.
  - Desarrollo: flask run (usa la variable FLASK_APP=wsgi.py)
  - Producción: gunicorn -k eventlet -w 1 wsgi:app
"""
from app import create_app
from app.extensions import socketio

app = create_app()

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
