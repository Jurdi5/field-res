"""Corre la API y el frontend en local con DynamoDB y SNS simulados (moto).

    pip install -r requirements-dev.txt
    python local/servidor.py

Abre http://localhost:8000
"""
import importlib
import json
import os
import re
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

RAIZ = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(RAIZ / "backend"), str(RAIZ)]

os.environ.update({
    "AWS_DEFAULT_REGION": "us-east-1",
    "AWS_ACCESS_KEY_ID": "local",
    "AWS_SECRET_ACCESS_KEY": "local",
    "TABLA_RESERVAS": "fieldres-reservas",
    "TABLA_SLOTS": "fieldres-slots",
    "TABLA_CANCHAS": "fieldres-canchas",
})

from moto import mock_aws  # noqa: E402

mock = mock_aws()
mock.start()

import boto3  # noqa: E402

ddb = boto3.client("dynamodb")
ddb.create_table(
    TableName="fieldres-reservas",
    BillingMode="PAY_PER_REQUEST",
    AttributeDefinitions=[
        {"AttributeName": "reservaId", "AttributeType": "S"},
        {"AttributeName": "userId", "AttributeType": "S"},
        {"AttributeName": "fechaHora", "AttributeType": "S"},
    ],
    KeySchema=[{"AttributeName": "reservaId", "KeyType": "HASH"}],
    GlobalSecondaryIndexes=[{
        "IndexName": "userId-index",
        "KeySchema": [
            {"AttributeName": "userId", "KeyType": "HASH"},
            {"AttributeName": "fechaHora", "KeyType": "RANGE"},
        ],
        "Projection": {"ProjectionType": "ALL"},
    }],
)
ddb.create_table(
    TableName="fieldres-slots",
    BillingMode="PAY_PER_REQUEST",
    AttributeDefinitions=[
        {"AttributeName": "canchaId", "AttributeType": "S"},
        {"AttributeName": "fechaHora", "AttributeType": "S"},
    ],
    KeySchema=[
        {"AttributeName": "canchaId", "KeyType": "HASH"},
        {"AttributeName": "fechaHora", "KeyType": "RANGE"},
    ],
)
ddb.create_table(
    TableName="fieldres-canchas",
    BillingMode="PAY_PER_REQUEST",
    AttributeDefinitions=[{"AttributeName": "canchaId", "AttributeType": "S"}],
    KeySchema=[{"AttributeName": "canchaId", "KeyType": "HASH"}],
)
for cid, nombre, tipo, precio in [
    ("cancha-1", "Cancha 1", "Panoramica", "450"),
    ("cancha-2", "Cancha 2", "Panoramica", "450"),
    ("cancha-3", "Cancha 3", "Techada", "500"),
]:
    ddb.put_item(TableName="fieldres-canchas", Item={
        "canchaId": {"S": cid}, "nombre": {"S": nombre}, "tipo": {"S": tipo},
        "precioHora": {"N": precio}, "activa": {"BOOL": True},
    })
os.environ["TOPIC_ARN"] = boto3.client("sns").create_topic(Name="reservas-eventos")["TopicArn"]

crear_reserva = importlib.import_module("crear_reserva")
consultas = importlib.import_module("consultas")
suscribir = importlib.import_module("suscribir")
try:
    cancelar_reserva = importlib.import_module("cancelar_reserva")
except ModuleNotFoundError:
    cancelar_reserva = None

RUTAS = [
    ("POST", r"/reservas", "POST /reservas", crear_reserva),
    ("GET", r"/reservas", "GET /reservas", consultas),
    ("GET", r"/canchas", "GET /canchas", consultas),
    ("GET", r"/canchas/(?P<canchaId>[^/]+)/disponibilidad", "GET /canchas/{canchaId}/disponibilidad", consultas),
    ("POST", r"/suscripciones", "POST /suscripciones", suscribir),
    ("DELETE", r"/reservas/(?P<reservaId>[^/]+)", "DELETE /reservas/{reservaId}", cancelar_reserva),
]


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(RAIZ / "frontend"), **kwargs)

    def _api(self, metodo):
        url = urlparse(self.path)
        if url.path == "/config.js":
            return self._enviar(200, 'window.FIELDRES_API = "/api";', "application/javascript")
        if not url.path.startswith("/api/"):
            return False
        ruta = url.path[4:]
        for m, patron, route_key, modulo in RUTAS:
            match = re.fullmatch(patron, ruta)
            if m == metodo and match:
                if modulo is None:
                    return self._enviar(501, json.dumps({"error": "cancelar_reserva.py no esta en esta rama"}))
                largo = int(self.headers.get("Content-Length") or 0)
                event = {
                    "routeKey": route_key,
                    "pathParameters": match.groupdict() or None,
                    "queryStringParameters": {k: v[0] for k, v in parse_qs(url.query).items()} or None,
                    "body": self.rfile.read(largo).decode() if largo else None,
                }
                res = modulo.lambda_handler(event, None)
                return self._enviar(res["statusCode"], res["body"])
        return self._enviar(404, json.dumps({"error": "Ruta no encontrada"}))

    def _enviar(self, status, body, tipo="application/json"):
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        return True

    def do_GET(self):
        if not self._api("GET"):
            super().do_GET()

    def do_POST(self):
        self._api("POST")

    def do_DELETE(self):
        self._api("DELETE")


if __name__ == "__main__":
    puerto = int(os.environ.get("PORT", "8000"))
    print(f"Field Res local en http://localhost:{puerto}")
    ThreadingHTTPServer(("127.0.0.1", puerto), Handler).serve_forever()
