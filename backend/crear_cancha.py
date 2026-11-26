import base64
import binascii
import json
import logging
import os
import re
import uuid

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.client("dynamodb")
s3 = boto3.client("s3")

TABLA_CANCHAS = os.environ["TABLA_CANCHAS"]
BUCKET_FOTOS = os.environ["BUCKET_FOTOS"]
REGION = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
FOTOS_URL_BASE = os.environ.get("FOTOS_URL_BASE") or f"https://{BUCKET_FOTOS}.s3.{REGION}.amazonaws.com"

TIPOS = {"Panoramica", "Techada", "Exterior"}
MAX_FOTO_BYTES = 4 * 1024 * 1024
FORMATOS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def _resp(status, body):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }


def _leer_foto(valor):
    """Recibe un data URL (data:image/jpeg;base64,...) y regresa (bytes, content_type)."""
    match = re.fullmatch(r"data:(image/[a-z]+);base64,(.+)", valor.strip(), re.S)
    if not match or match.group(1) not in FORMATOS:
        raise ValueError("La foto debe ser JPG, PNG o WEBP")
    try:
        datos = base64.b64decode(match.group(2), validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("La foto no es base64 valido")
    if not datos:
        raise ValueError("La foto esta vacia")
    if len(datos) > MAX_FOTO_BYTES:
        raise ValueError("La foto pesa mas de 4 MB")
    return datos, match.group(1)


def lambda_handler(event, context):
    # 1. Validacion del input
    try:
        body = json.loads(event.get("body") or "{}")
        nombre = str(body["nombre"]).strip()
        tipo = str(body.get("tipo") or "Panoramica").strip()
        precio = int(body["precioHora"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return _resp(400, {"error": "Se requieren nombre y precioHora (numero entero)"})

    if not 1 <= len(nombre) <= 40:
        return _resp(400, {"error": "El nombre debe tener entre 1 y 40 caracteres"})
    if tipo not in TIPOS:
        return _resp(400, {"error": f"El tipo debe ser uno de: {', '.join(sorted(TIPOS))}"})
    if not 1 <= precio <= 10000:
        return _resp(400, {"error": "El precio por hora debe estar entre 1 y 10000"})

    foto = None
    if body.get("foto"):
        try:
            foto = _leer_foto(body["foto"])
        except ValueError as e:
            return _resp(400, {"error": str(e)})

    cancha_id = f"cancha-{uuid.uuid4().hex[:8]}"
    item = {
        "canchaId": {"S": cancha_id},
        "nombre": {"S": nombre},
        "tipo": {"S": tipo},
        "precioHora": {"N": str(precio)},
        "activa": {"BOOL": True},
    }

    # 2. Subir la foto a S3 (si falla no se crea la cancha)
    imagen_url = ""
    if foto:
        datos, content_type = foto
        llave = f"canchas/{cancha_id}.{FORMATOS[content_type]}"
        try:
            s3.put_object(Bucket=BUCKET_FOTOS, Key=llave, Body=datos, ContentType=content_type)
        except ClientError:
            logger.exception("Error subiendo la foto")
            return _resp(500, {"error": "No se pudo guardar la foto"})
        imagen_url = f"{FOTOS_URL_BASE}/{llave}"
        item["imagenUrl"] = {"S": imagen_url}

    # 3. Guardar la cancha
    try:
        dynamodb.put_item(
            TableName=TABLA_CANCHAS,
            Item=item,
            ConditionExpression="attribute_not_exists(canchaId)",
        )
    except ClientError:
        logger.exception("Error guardando la cancha")
        return _resp(500, {"error": "Error interno"})

    cancha = {
        "canchaId": cancha_id,
        "nombre": nombre,
        "tipo": tipo,
        "precioHora": precio,
        "activa": True,
        "imagenUrl": imagen_url,
    }
    return _resp(201, {"mensaje": "Cancha creada", "cancha": cancha})
