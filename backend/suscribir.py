import json
import logging
import os
import re

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sns = boto3.client("sns")

TOPIC_ARN = os.environ["TOPIC_ARN"]


def _resp(status, body):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }


def _suscripcion_existente(correo):
    params = {"TopicArn": TOPIC_ARN}
    while True:
        res = sns.list_subscriptions_by_topic(**params)
        for s in res["Subscriptions"]:
            if s["Protocol"] == "email" and s["Endpoint"].lower() == correo:
                return s["SubscriptionArn"]
        if "NextToken" not in res:
            return None
        params["NextToken"] = res["NextToken"]


def lambda_handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
        correo = body["userId"].strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", correo):
            raise ValueError("correo invalido")
    except (KeyError, TypeError, ValueError, AttributeError):
        return _resp(400, {"error": "Se requiere userId con un correo valido"})

    try:
        arn = _suscripcion_existente(correo)
        if arn and arn != "PendingConfirmation":
            return _resp(200, {"estado": "CONFIRMADA"})
        if arn == "PendingConfirmation":
            return _resp(200, {"estado": "PENDIENTE"})

        sns.subscribe(
            TopicArn=TOPIC_ARN,
            Protocol="email",
            Endpoint=correo,
            Attributes={"FilterPolicy": json.dumps({"userId": [correo]})},
        )
    except ClientError:
        logger.exception("Error suscribiendo el correo")
        return _resp(500, {"error": "Error interno"})

    return _resp(202, {"estado": "PENDIENTE", "mensaje": "Revisa tu correo para confirmar la suscripcion"})
