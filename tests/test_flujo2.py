import json
from datetime import datetime, timedelta, timezone

from conftest import cargar, evento_post, manana


def reservar(aws, user="ana@test.com", hora=10):
    m = cargar("crear_reserva")
    fecha_hora, _ = manana(hora)
    res = m.lambda_handler(evento_post({"userId": user, "canchaId": "cancha-1", "fechaHora": fecha_hora}), None)
    assert res["statusCode"] == 201
    return json.loads(res["body"])


def cancelar(reserva_id, user="ana@test.com"):
    m = cargar("cancelar_reserva")
    event = {"pathParameters": {"reservaId": reserva_id}, "body": json.dumps({"userId": user})}
    res = m.lambda_handler(event, None)
    return res["statusCode"], json.loads(res["body"])


def test_cancela_y_libera_horario(aws):
    r = reservar(aws)
    status, body = cancelar(r["reservaId"])

    assert status == 200
    item = aws.get_item(TableName="reservas", Key={"reservaId": {"S": r["reservaId"]}})["Item"]
    assert item["estado"]["S"] == "CANCELADA"
    assert "canceladaEn" in item
    slot = aws.get_item(TableName="slots", Key={"canchaId": {"S": "cancha-1"}, "fechaHora": {"S": r["fechaHora"]}})
    assert "Item" not in slot


def test_el_horario_se_puede_volver_a_reservar(aws):
    r = reservar(aws)
    cancelar(r["reservaId"])
    otra = reservar(aws, user="beto@test.com")
    assert otra["fechaHora"] == r["fechaHora"]


def test_normaliza_el_correo(aws):
    r = reservar(aws)
    status, _ = cancelar(r["reservaId"], user="  ANA@Test.com ")
    assert status == 200


def test_no_cancela_reserva_de_otro(aws):
    r = reservar(aws)
    status, _ = cancelar(r["reservaId"], user="beto@test.com")
    assert status == 403


def test_reserva_inexistente(aws):
    status, _ = cancelar("no-existe")
    assert status == 404


def test_no_cancela_dos_veces(aws):
    r = reservar(aws)
    cancelar(r["reservaId"])
    status, _ = cancelar(r["reservaId"])
    assert status == 409


def test_fuera_de_la_ventana_de_cancelacion(aws):
    pronto = (datetime.now(timezone.utc) + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    aws.put_item(TableName="reservas", Item={
        "reservaId": {"S": "r-pronto"}, "userId": {"S": "ana@test.com"}, "canchaId": {"S": "cancha-1"},
        "fechaHora": {"S": pronto}, "estado": {"S": "CONFIRMADA"},
    })
    status, body = cancelar("r-pronto")
    assert status == 409
    assert "anticipacion" in body["error"]


def test_valida_entrada(aws):
    m = cargar("cancelar_reserva")
    res = m.lambda_handler({"pathParameters": {"reservaId": "x"}, "body": "{}"}, None)
    assert res["statusCode"] == 400
