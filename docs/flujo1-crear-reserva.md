# Flujo 1: Crear reserva

El usuario elige cancha, fecha y horario desde el frontend y reserva. Si el horario sigue libre la reserva se confirma y se manda un correo. Si alguien mas lo tomo antes, recibe un error y el horario aparece como ocupado.

## Pasos

1. El frontend (S3) pide las canchas (`GET /canchas`) y los horarios del dia (`GET /canchas/{canchaId}/disponibilidad?fecha=`).
2. El usuario elige un horario libre y manda `POST /reservas`.
3. La Lambda `fieldres-crear-reserva` valida los datos:
   - `fechaHora` en ISO 8601 y en hora completa (las reservas son de 1 hora)
   - el horario es futuro, dentro de 30 dias y dentro del horario del club (7:00 a 23:00, hora de Guadalajara)
   - la cancha existe y esta activa
4. En una sola transaccion de DynamoDB:
   - crea el slot `(canchaId, fechaHora)` en la tabla de slots con la condicion `attribute_not_exists`
   - crea la reserva con estado `CONFIRMADA`
5. Publica el evento `CONFIRMADA` en el topico SNS `reservas-eventos`. Los suscriptores por correo reciben un mensaje legible; otros suscriptores (por ejemplo una cola SQS) reciben el JSON del evento.

## Por que no hay dobles reservas

La tabla de slots tiene como llave `canchaId + fechaHora`, asi que solo puede existir un item por horario. La escritura es condicional: si dos personas reservan el mismo horario al mismo tiempo, DynamoDB acepta solo la primera y la otra transaccion se cancela completa (no queda una reserva sin slot ni un slot sin reserva). La Lambda responde `409` a la segunda.

Esto esta probado en `tests/test_flujo1.py` con 5 reservas simultaneas al mismo horario: solo una gana.

## Endpoints

### `POST /reservas`

```json
{ "userId": "ana@correo.com", "canchaId": "cancha-1", "fechaHora": "2026-10-20T00:00:00Z" }
```

| Codigo | Caso |
|--------|------|
| 201 | Reserva confirmada |
| 400 | Datos invalidos, horario pasado, fuera del horario del club o no es hora completa |
| 404 | La cancha no existe o esta inactiva |
| 409 | El horario ya esta reservado |
| 500 | Error interno |

Respuesta `201`:

```json
{
  "mensaje": "Reserva confirmada",
  "reservaId": "7152d197-e392-40ac-8ed7-5f90be93512b",
  "userId": "ana@correo.com",
  "canchaId": "cancha-1",
  "fechaHora": "2026-10-20T00:00:00Z",
  "tipo": "CONFIRMADA"
}
```

### `GET /canchas/{canchaId}/disponibilidad?fecha=YYYY-MM-DD`

`fecha` es el dia en hora local del club. Regresa un horario por hora con `disponible` y `ocupado`.

### `GET /reservas?userId=`

Reservas del usuario, de la mas reciente a la mas antigua. Usa el indice `userId-index`.

### `POST /suscripciones`

```json
{ "userId": "ana@correo.com" }
```

Suscribe el correo al topico con un filtro por `userId`, para que cada usuario reciba solo sus notificaciones. AWS manda un correo de confirmacion que hay que aceptar antes de recibir avisos.

## Modelo de datos

**fieldres-reservas** (llave `reservaId`, indice `userId-index` con `userId + fechaHora`)

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `reservaId` | S | UUID |
| `userId` | S | Correo del usuario en minusculas |
| `canchaId` | S | Cancha reservada |
| `fechaHora` | S | Inicio en UTC, formato `YYYY-MM-DDTHH:00:00Z` |
| `estado` | S | `CONFIRMADA` o `CANCELADA` |
| `creadaEn` | S | Fecha de creacion |

**fieldres-slots** (llave `canchaId + fechaHora`): un item por horario ocupado, con el `reservaId` que lo ocupa. El flujo 2 lo borra al cancelar.

**fieldres-canchas** (llave `canchaId`): `nombre`, `tipo`, `precioHora`, `activa`. `crear.sh` carga 3 canchas de ejemplo; el flujo 3 da de alta las demas.

## Decisiones tecnicas

- **Tabla de slots separada:** la condicion de unicidad vive en la llave primaria, que es lo unico que DynamoDB puede garantizar de forma atomica. Con una sola tabla habria que hacer una consulta antes de escribir y dos usuarios podrian pasar la consulta al mismo tiempo.
- **Fechas en UTC:** todas las fechas se guardan en UTC con el mismo formato para que la llave del slot sea siempre igual sin importar como la mande el cliente. La conversion a hora local se hace solo para validar el horario del club y para mostrar.
- **Correo como `userId`:** para esta fase no hay login; el correo identifica al usuario y sirve para filtrar las notificaciones de SNS.
- **La notificacion no revierte la reserva:** si SNS falla, la reserva se queda y el error se registra en CloudWatch.
- **HTTP API en lugar de REST API:** es mas barata, tiene CORS integrado y basta para lo que necesitamos.
- **Frontend sin framework:** HTML, CSS y JS sin build, se sube tal cual a S3.
