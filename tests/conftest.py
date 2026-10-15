import importlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

RAIZ = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(RAIZ / "backend"), str(RAIZ)]

ZONA_CLUB = timezone(timedelta(hours=-6))


@pytest.fixture
def aws(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    with mock_aws():
        ddb = boto3.client("dynamodb")
        ddb.create_table(
            TableName="reservas",
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
            TableName="slots",
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
            TableName="canchas",
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[{"AttributeName": "canchaId", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "canchaId", "KeyType": "HASH"}],
        )
        ddb.put_item(TableName="canchas", Item={
            "canchaId": {"S": "cancha-1"}, "nombre": {"S": "Cancha 1"},
            "precioHora": {"N": "450"}, "activa": {"BOOL": True},
        })
        ddb.put_item(TableName="canchas", Item={
            "canchaId": {"S": "cancha-x"}, "nombre": {"S": "Cerrada"},
            "precioHora": {"N": "450"}, "activa": {"BOOL": False},
        })
        topic = boto3.client("sns").create_topic(Name="reservas-eventos")["TopicArn"]

        monkeypatch.setenv("TABLA_RESERVAS", "reservas")
        monkeypatch.setenv("TABLA_SLOTS", "slots")
        monkeypatch.setenv("TABLA_CANCHAS", "canchas")
        monkeypatch.setenv("TOPIC_ARN", topic)
        yield ddb


def cargar(modulo):
    if modulo in sys.modules:
        return importlib.reload(sys.modules[modulo])
    return importlib.import_module(modulo)


def manana(hora_local):
    dia = datetime.now(ZONA_CLUB) + timedelta(days=1)
    local = dia.replace(hour=hora_local, minute=0, second=0, microsecond=0)
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), local.strftime("%Y-%m-%d")


def evento_post(body):
    return {"body": json.dumps(body)}
