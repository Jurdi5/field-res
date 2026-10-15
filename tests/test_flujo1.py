import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from conftest import cargar, evento_post, manana


def crear(modulo, **body):
    base = {"userId": "ana@test.com", "canchaId": "cancha-1"}
    base.update(body)
    res = modulo.lambda_handler(evento_post(base), None)
    return res["statusCode"], json.loads(res["body"])


def test_crea_reserva_y_ocupa_horario(aws):
    m = cargar("crear_reserva")
    fecha_hora, _ = manana(10)
    status, body = crear(m, fechaHora=fecha_hora)

    assert status == 201
    reserva = aws.get_item(TableName="reservas", Key={"reservaId": {"S": body["reservaId"]}})["Item"]
    assert reserva["estado"]["S"] == "CONFIRMADA"
    assert reserva["fechaHora"]["S"] == fecha_hora
    slot = aws.get_item(TableName="slots", Key={"canchaId": {"S": "cancha-1"}, "fechaHora": {"S": fecha_hora}})
    assert slot["Item"]["reservaId"]["S"] == body["reservaId"]


def test_normaliza_fecha_con_zona(aws):
    m = cargar("crear_reserva")
    fecha_hora, _ = manana(10)
    local = fecha_hora.replace("Z", "+00:00")
    status, body = crear(m, fechaHora=local, userId="  ANA@Test.com ")
    assert status == 201
    assert body["fechaHora"] == fecha_hora
    assert body["userId"] == "ana@test.com"


def test_no_permite_doble_reserva(aws):
    m = cargar("crear_reserva")
    fecha_hora, _ = manana(18)
    assert crear(m, fechaHora=fecha_hora)[0] == 201
    status, body = crear(m, fechaHora=fecha_hora, userId="beto@test.com")
    assert status == 409
    assert aws.scan(TableName="reservas")["Count"] == 1


def test_reservas_simultaneas_solo_una_gana(aws):
    m = cargar("crear_reserva")
    fecha_hora, _ = manana(20)
    with ThreadPoolExecutor(5) as ex:
        resultados = list(ex.map(lambda i: crear(m, fechaHora=fecha_hora, userId=f"u{i}@test.com")[0], range(5)))
    assert resultados.count(201) == 1
    assert resultados.count(409) == 4


@pytest.mark.parametrize("body,esperado", [
    ({}, 400),
    ({"canchaId": "cancha-1", "fechaHora": "2030-01-01T10:00:00Z"}, 400),
    ({"userId": "a@test.com", "canchaId": "cancha-1", "fechaHora": "no-es-fecha"}, 400),
    ({"userId": "a@test.com", "canchaId": "cancha-1", "fechaHora": "2020-01-01T16:00:00Z"}, 400),
])
def test_valida_entrada(aws, body, esperado):
    m = cargar("crear_reserva")
    res = m.lambda_handler(evento_post(body), None)
    assert res["statusCode"] == esperado


def test_rechaza_media_hora_y_fuera_de_horario(aws):
    m = cargar("crear_reserva")
    fecha_hora, _ = manana(10)
    assert crear(m, fechaHora=fecha_hora.replace(":00:00Z", ":30:00Z"))[0] == 400
    madrugada, _ = manana(3)
    assert crear(m, fechaHora=madrugada)[0] == 400


def test_cancha_inexistente_o_inactiva(aws):
    m = cargar("crear_reserva")
    fecha_hora, _ = manana(10)
    assert crear(m, fechaHora=fecha_hora, canchaId="no-existe")[0] == 404
    assert crear(m, fechaHora=fecha_hora, canchaId="cancha-x")[0] == 404


def test_disponibilidad_y_mis_reservas(aws):
    crear_m = cargar("crear_reserva")
    consultas = cargar("consultas")
    fecha_hora, fecha = manana(9)
    crear(crear_m, fechaHora=fecha_hora)

    res = consultas.lambda_handler({
        "routeKey": "GET /canchas/{canchaId}/disponibilidad",
        "pathParameters": {"canchaId": "cancha-1"},
        "queryStringParameters": {"fecha": fecha},
    }, None)
    horarios = json.loads(res["body"])["horarios"]
    assert len(horarios) == 16
    nueve = next(h for h in horarios if h["hora"] == "09:00")
    assert nueve["fechaHora"] == fecha_hora
    assert nueve["disponible"] is False and nueve["ocupado"] is True
    assert next(h for h in horarios if h["hora"] == "10:00")["disponible"] is True

    res = consultas.lambda_handler({
        "routeKey": "GET /reservas",
        "queryStringParameters": {"userId": "ana@test.com"},
    }, None)
    reservas = json.loads(res["body"])
    assert len(reservas) == 1 and reservas[0]["canchaId"] == "cancha-1"

    res = consultas.lambda_handler({"routeKey": "GET /canchas"}, None)
    canchas = json.loads(res["body"])
    assert [c["canchaId"] for c in canchas] == ["cancha-1"]


def test_cancelar_libera_horario(aws, monkeypatch):
    try:
        cancelar = cargar("cancelar_reserva")
    except ModuleNotFoundError:
        pytest.skip("cancelar_reserva.py (flujo 2) no esta en esta rama")
    m = cargar("crear_reserva")
    fecha_hora, _ = manana(12)
    _, body = crear(m, fechaHora=fecha_hora)

    res = cancelar.lambda_handler({
        "pathParameters": {"reservaId": body["reservaId"]},
        "body": json.dumps({"userId": "ana@test.com"}),
    }, None)
    assert res["statusCode"] == 200
    assert crear(m, fechaHora=fecha_hora, userId="beto@test.com")[0] == 201
