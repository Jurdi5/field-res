import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.client("dynamodb")
sns = boto3.client("sns")

TABLA_RESERVAS = os.environ["TABLA_RESERVAS"]
TABLA_SLOTS = os.environ["TABLA_SLOTS"]
TABLA_CANCHAS = os.environ["TABLA_CANCHAS"]
TOPIC_ARN = os.environ["TOPIC_ARN"]
UTC_OFFSET = int(os.environ.get("UTC_OFFSET", "-6"))
HORA_APERTURA = int(os.environ.get("HORA_APERTURA", "7"))
HORA_CIERRE = int(os.environ.get("HORA_CIERRE", "23"))
DIAS_MAX_ANTICIPACION = int(os.environ.get("DIAS_MAX_ANTICIPACION", "30"))

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


def _normalizar_fecha(valor):
    fecha = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)
    fecha = fecha.astimezone(timezone.utc)
    if fecha.minute or fecha.second or fecha.microsecond:
        raise ValueError("los horarios son por hora completa")
    return fecha


def _validar_horario(fecha):
    ahora = datetime.now(timezone.utc)
    if fecha <= ahora:
        return "No se puede reservar en un horario que ya paso"
    if fecha > ahora + timedelta(days=DIAS_MAX_ANTICIPACION):
        return f"Solo se puede reservar con {DIAS_MAX_ANTICIPACION} dias de anticipacion"
    hora_local = fecha.astimezone(ZONA_CLUB).hour
    if not HORA_APERTURA <= hora_local < HORA_CIERRE:
        return f"El club abre de {HORA_APERTURA}:00 a {HORA_CIERRE}:00"
    return None


def _mensaje_correo(evento, nombre_cancha):
    local = datetime.fromisoformat(evento["fechaHora"].replace("Z", "+00:00")).astimezone(ZONA_CLUB)
    return (
        "Tu reserva en Field Res quedo confirmada.\n\n"
        f"Cancha: {nombre_cancha}\n"
        f"Fecha: {local.strftime('%d/%m/%Y')}\n"
        f"Hora: {local.strftime('%H:%M')}\n"
        f"Folio: {evento['reservaId']}\n"
    )


def lambda_handler(event, context):
    # 1. Validacion del input
    try:
        body = json.loads(event.get("body") or "{}")
        user_id = body["userId"].strip().lower()
        cancha_id = body["canchaId"].strip()
        fecha = _normalizar_fecha(body["fechaHora"])
        if not user_id or not cancha_id:
            raise ValueError("vacio")
    except (KeyError, TypeError, ValueError, AttributeError):
        return _resp(400, {"error": "Se requieren userId, canchaId y fechaHora (ISO 8601, hora completa)"})

    error = _validar_horario(fecha)
    if error:
        return _resp(400, {"error": error})

    fecha_hora = fecha.strftime("%Y-%m-%dT%H:%M:%SZ")

    # 2. Verificar que la cancha exista y este activa
    try:
        res = dynamodb.get_item(TableName=TABLA_CANCHAS, Key={"canchaId": {"S": cancha_id}})
    except ClientError:
        logger.exception("Error leyendo la cancha")
        return _resp(500, {"error": "Error interno"})

    cancha = res.get("Item")
    if not cancha or not cancha.get("activa", {}).get("BOOL", True):
        return _resp(404, {"error": "La cancha no existe o no esta disponible"})
    nombre_cancha = cancha.get("nombre", {}).get("S", cancha_id)

    # 3. Ocupar el horario y crear la reserva en una sola transaccion
    reserva_id = str(uuid.uuid4())
    ahora = datetime.now(timezone.utc).isoformat()
    try:
        dynamodb.transact_write_items(
            TransactItems=[
                {
                    "Put": {
                        "TableName": TABLA_SLOTS,
                        "Item": {
                            "canchaId": {"S": cancha_id},
                            "fechaHora": {"S": fecha_hora},
                            "reservaId": {"S": reserva_id},
                        },
                        "ConditionExpression": "attribute_not_exists(canchaId)",
                    }
                },
                {
                    "Put": {
                        "TableName": TABLA_RESERVAS,
                        "Item": {
                            "reservaId": {"S": reserva_id},
                            "userId": {"S": user_id},
                            "canchaId": {"S": cancha_id},
                            "fechaHora": {"S": fecha_hora},
                            "estado": {"S": "CONFIRMADA"},
                            "creadaEn": {"S": ahora},
                        },
                        "ConditionExpression": "attribute_not_exists(reservaId)",
                    }
                },
            ]
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "TransactionCanceledException":
            return _resp(409, {"error": "Ese horario ya esta reservado"})
        logger.exception("Error creando la reserva")
        return _resp(500, {"error": "Error interno"})

    # 4. Notificar (si SNS falla la reserva se queda)
    evento = {
        "reservaId": reserva_id,
        "userId": user_id,
        "canchaId": cancha_id,
        "fechaHora": fecha_hora,
        "tipo": "CONFIRMADA",
    }
    try:
        sns.publish(
            TopicArn=TOPIC_ARN,
            Subject="Reserva confirmada - Field Res",
            MessageStructure="json",
            Message=json.dumps({
                "default": json.dumps(evento),
                "email": _mensaje_correo(evento, nombre_cancha),
            }),
            MessageAttributes={
                "tipo": {"DataType": "String", "StringValue": "CONFIRMADA"},
                "userId": {"DataType": "String", "StringValue": user_id},
            },
        )
    except ClientError:
        logger.exception("No se pudo publicar la notificacion")

    return _resp(201, {"mensaje": "Reserva confirmada", **evento})
