import base64
import json

import boto3

from conftest import cargar, evento_post

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


def crear(**body):
    m = cargar("crear_cancha")
    res = m.lambda_handler(evento_post(body), None)
    return res["statusCode"], json.loads(res["body"])


def foto(datos=PNG_1PX, tipo="image/png"):
    return f"data:{tipo};base64,{base64.b64encode(datos).decode()}"


def test_crea_cancha_sin_foto(aws):
    status, body = crear(nombre="Cancha 4", tipo="Techada", precioHora=500)

    assert status == 201
    cancha = body["cancha"]
    assert cancha["imagenUrl"] == ""
    item = aws.get_item(TableName="canchas", Key={"canchaId": {"S": cancha["canchaId"]}})["Item"]
    assert item["nombre"]["S"] == "Cancha 4"
    assert item["precioHora"]["N"] == "500"
    assert item["activa"]["BOOL"] is True


def test_crea_cancha_con_foto_en_s3(aws):
    status, body = crear(nombre="Cancha 5", precioHora=450, foto=foto())

    assert status == 201
    cancha = body["cancha"]
    llave = f"canchas/{cancha['canchaId']}.png"
    assert cancha["imagenUrl"].endswith(f"/fotos/{llave}") or cancha["imagenUrl"].endswith(llave)
    obj = boto3.client("s3").get_object(Bucket="fotos", Key=llave)
    assert obj["Body"].read() == PNG_1PX
    assert obj["ContentType"] == "image/png"


def test_la_cancha_nueva_aparece_para_reservar(aws):
    _, body = crear(nombre="Cancha 6", precioHora=400, foto=foto())
    consultas = cargar("consultas")
    res = consultas.lambda_handler({"routeKey": "GET /canchas"}, None)
    canchas = {c["canchaId"]: c for c in json.loads(res["body"])}
    nueva = canchas[body["cancha"]["canchaId"]]
    assert nueva["nombre"] == "Cancha 6"
    assert nueva["imagenUrl"] == body["cancha"]["imagenUrl"]


def test_se_puede_reservar_la_cancha_nueva(aws):
    from conftest import manana

    _, body = crear(nombre="Cancha 7", precioHora=400)
    fecha_hora, _ = manana(12)
    m = cargar("crear_reserva")
    res = m.lambda_handler(evento_post({
        "userId": "ana@test.com", "canchaId": body["cancha"]["canchaId"], "fechaHora": fecha_hora,
    }), None)
    assert res["statusCode"] == 201


def test_requiere_nombre_y_precio(aws):
    assert crear(precioHora=450)[0] == 400
    assert crear(nombre="Sin precio")[0] == 400
    assert crear(nombre="   ", precioHora=450)[0] == 400


def test_valida_tipo_y_precio(aws):
    assert crear(nombre="X", tipo="Pasto", precioHora=450)[0] == 400
    assert crear(nombre="X", precioHora=0)[0] == 400
    assert crear(nombre="X", precioHora="caro")[0] == 400


def test_rechaza_foto_invalida(aws):
    assert crear(nombre="X", precioHora=450, foto="no-es-imagen")[0] == 400
    assert crear(nombre="X", precioHora=450, foto=foto(tipo="image/gif"))[0] == 400
    assert crear(nombre="X", precioHora=450, foto="data:image/png;base64,%%%")[0] == 400


def test_rechaza_foto_muy_grande(aws):
    status, body = crear(nombre="X", precioHora=450, foto=foto(b"0" * (4 * 1024 * 1024 + 1)))
    assert status == 400
    assert "4 MB" in body["error"]
    assert boto3.client("s3").list_objects_v2(Bucket="fotos").get("KeyCount", 0) == 0
