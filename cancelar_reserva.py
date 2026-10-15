import json
import logging
import os
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.client("dynamodb")
sns = boto3.client("sns")

TABLA_RESERVAS = os.environ["TABLA_RESERVAS"]
TABLA_SLOTS = os.environ["TABLA_SLOTS"]
TOPIC_ARN = os.environ["TOPIC_ARN"]
HORAS_MIN_CANCELACION = int(os.environ.get("HORAS_MIN_CANCELACION", "1"))


def _resp(status, body):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }


def _parse_fecha(valor):
    fecha = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)
    return fecha


def lambda_handler(event, context):
    # 1. Validacion del input
    try:
        reserva_id = event["pathParameters"]["reservaId"]
        body = json.loads(event.get("body") or "{}")
        user_id = body["userId"]
        if not reserva_id or not user_id:
            raise ValueError("vacio")
    except (KeyError, TypeError, ValueError):
        return _resp(400, {"error": "Se requieren reservaId (ruta) y userId (body)"})

    # 2. Buscar la reserva
    try:
        res = dynamodb.get_item(
            TableName=TABLA_RESERVAS,
            Key={"reservaId": {"S": reserva_id}},
        )
    except ClientError:
        logger.exception("Error leyendo la reserva")
        return _resp(500, {"error": "Error interno"})

    item = res.get("Item")
    if not item:
        return _resp(404, {"error": "Reserva no encontrada"})

    # 3. Reglas de negocio
    if item["userId"]["S"] != user_id:
        return _resp(403, {"error": "La reserva no pertenece a este usuario"})

    if item["estado"]["S"] != "CONFIRMADA":
        return _resp(409, {"error": "La reserva ya no esta activa"})

    cancha_id = item["canchaId"]["S"]
    fecha_hora = item["fechaHora"]["S"]

    limite = _parse_fecha(fecha_hora) - timedelta(hours=HORAS_MIN_CANCELACION)
    if datetime.now(timezone.utc) > limite:
        return _resp(
            409,
            {"error": f"Solo se puede cancelar con {HORAS_MIN_CANCELACION} hora(s) de anticipacion"},
        )

    # 4. Cancelar y liberar el horario de forma atomica
    ahora = datetime.now(timezone.utc).isoformat()
    try:
        dynamodb.transact_write_items(
            TransactItems=[
                {
                    "Update": {
                        "TableName": TABLA_RESERVAS,
                        "Key": {"reservaId": {"S": reserva_id}},
                        "UpdateExpression": "SET estado = :nuevo, canceladaEn = :ahora",
                        "ConditionExpression": "estado = :actual",
                        "ExpressionAttributeValues": {
                            ":nuevo": {"S": "CANCELADA"},
                            ":actual": {"S": "CONFIRMADA"},
                            ":ahora": {"S": ahora},
                        },
                    }
                },
                {
                    "Delete": {
                        "TableName": TABLA_SLOTS,
                        "Key": {
                            "canchaId": {"S": cancha_id},
                            "fechaHora": {"S": fecha_hora},
                        },
                    }
                },
            ]
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "TransactionCanceledException":
            # Alguien la cancelo al mismo tiempo
            return _resp(409, {"error": "La reserva ya fue cancelada"})
        logger.exception("Error cancelando la reserva")
        return _resp(500, {"error": "Error interno"})

    # 5. Notificar (la reserva ya esta cancelada; si SNS falla no se revierte)
    evento = {
        "reservaId": reserva_id,
        "userId": user_id,
        "canchaId": cancha_id,
        "fechaHora": fecha_hora,
        "tipo": "CANCELADA",
    }
    try:
        sns.publish(
            TopicArn=TOPIC_ARN,
            Subject="Reserva cancelada - Field Res",
            Message=json.dumps(evento),
            MessageAttributes={
                "tipo": {"DataType": "String", "StringValue": "CANCELADA"},
                "userId": {"DataType": "String", "StringValue": user_id},
            },
        )
    except ClientError:
        logger.exception("No se pudo publicar la notificacion")

    return _resp(200, {"mensaje": "Reserva cancelada", "reservaId": reserva_id})