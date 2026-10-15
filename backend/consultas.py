import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.client("dynamodb")

TABLA_RESERVAS = os.environ["TABLA_RESERVAS"]
TABLA_SLOTS = os.environ["TABLA_SLOTS"]
TABLA_CANCHAS = os.environ["TABLA_CANCHAS"]
INDICE_USUARIO = os.environ.get("INDICE_USUARIO", "userId-index")
UTC_OFFSET = int(os.environ.get("UTC_OFFSET", "-6"))
HORA_APERTURA = int(os.environ.get("HORA_APERTURA", "7"))
HORA_CIERRE = int(os.environ.get("HORA_CIERRE", "23"))

ZONA_CLUB = timezone(timedelta(hours=UTC_OFFSET))


def _resp(status, body):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }


def _valor(attr):
    tipo, valor = next(iter(attr.items()))
    if tipo == "N":
        return float(valor) if "." in valor else int(valor)
    return valor


def _limpiar(item):
    return {k: _valor(v) for k, v in item.items()}


def listar_canchas(event):
    items = []
    params = {"TableName": TABLA_CANCHAS}
    while True:
        res = dynamodb.scan(**params)
        items += [_limpiar(i) for i in res["Items"]]
        if "LastEvaluatedKey" not in res:
            break
        params["ExclusiveStartKey"] = res["LastEvaluatedKey"]
    activas = [c for c in items if c.get("activa", True)]
    return _resp(200, sorted(activas, key=lambda c: c.get("nombre", c["canchaId"])))


def disponibilidad(event):
    cancha_id = (event.get("pathParameters") or {}).get("canchaId")
    fecha = (event.get("queryStringParameters") or {}).get("fecha", "")
    if not cancha_id or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", fecha):
        return _resp(400, {"error": "Se requiere canchaId y fecha (YYYY-MM-DD)"})

    dia = datetime.strptime(fecha, "%Y-%m-%d").replace(tzinfo=ZONA_CLUB)
    horarios = [dia.replace(hour=h) for h in range(HORA_APERTURA, HORA_CIERRE)]
    desde = horarios[0].astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    hasta = horarios[-1].astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    res = dynamodb.query(
        TableName=TABLA_SLOTS,
        KeyConditionExpression="canchaId = :c AND fechaHora BETWEEN :d AND :h",
        ExpressionAttributeValues={
            ":c": {"S": cancha_id},
            ":d": {"S": desde},
            ":h": {"S": hasta},
        },
    )
    ocupados = {i["fechaHora"]["S"] for i in res["Items"]}
    ahora = datetime.now(timezone.utc)

    resultado = []
    for h in horarios:
        utc = h.astimezone(timezone.utc)
        clave = utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        resultado.append({
            "hora": h.strftime("%H:%M"),
            "fechaHora": clave,
            "disponible": clave not in ocupados and utc > ahora,
            "ocupado": clave in ocupados,
        })
    return _resp(200, {"canchaId": cancha_id, "fecha": fecha, "horarios": resultado})


def reservas_usuario(event):
    user_id = ((event.get("queryStringParameters") or {}).get("userId") or "").strip().lower()
    if not user_id:
        return _resp(400, {"error": "Se requiere userId"})

    res = dynamodb.query(
        TableName=TABLA_RESERVAS,
        IndexName=INDICE_USUARIO,
        KeyConditionExpression="userId = :u",
        ExpressionAttributeValues={":u": {"S": user_id}},
    )
    reservas = sorted((_limpiar(i) for i in res["Items"]), key=lambda r: r["fechaHora"], reverse=True)
    return _resp(200, reservas)


RUTAS = {
    "GET /canchas": listar_canchas,
    "GET /canchas/{canchaId}/disponibilidad": disponibilidad,
    "GET /reservas": reservas_usuario,
}


def lambda_handler(event, context):
    ruta = RUTAS.get(event.get("routeKey"))
    if not ruta:
        return _resp(404, {"error": "Ruta no encontrada"})
    try:
        return ruta(event)
    except ClientError:
        logger.exception("Error consultando DynamoDB")
        return _resp(500, {"error": "Error interno"})
