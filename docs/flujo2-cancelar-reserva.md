# Flujo 2: Cancelar reserva (Field Res)

Función Lambda que cancela la reserva de una cancha de pádel, libera el horario y notifica al usuario. Forma parte del proyecto Field Res (Proyecto Integrador de Desarrollo en la Nube, ITESO, otoño 2026).

> Los campos marcados con `<TODO>` dependen de la infraestructura real. Reemplázalos antes de entregar.

## Qué hace

1. Recibe `reservaId` (en la ruta) y `userId` (en el body) a través de API Gateway.
2. Valida la entrada.
3. Busca la reserva en DynamoDB y verifica que exista, que pertenezca al usuario y que siga activa.
4. Verifica la ventana de cancelación (por defecto, al menos 1 hora antes de la reserva).
5. Cambia el estado a `CANCELADA` y libera el horario en una sola transacción de DynamoDB.
6. Publica un evento `CANCELADA` en el tópico SNS `reservas-eventos`, que se entrega por correo al usuario.

## Servicios de AWS que usa

| Servicio | Uso en este flujo |
|----------|-------------------|
| API Gateway | Expone el endpoint de cancelación |
| Lambda | Ejecuta la lógica de negocio |
| DynamoDB | Guarda la reserva y el bloqueo del horario |
| SNS | Notifica la cancelación al usuario |
| CloudWatch | Logs de la función y métricas |

## Endpoint

```
DELETE /reservas/{reservaId}
Content-Type: application/json

{ "userId": "<USER_ID>" }
```

### Respuestas

| Código | Caso |
|--------|------|
| 200 | Reserva cancelada |
| 400 | Falta `reservaId` o `userId` |
| 403 | La reserva pertenece a otro usuario |
| 404 | La reserva no existe |
| 409 | Ya estaba cancelada, está fuera de la ventana de cancelación o se canceló al mismo tiempo |
| 500 | Error interno |

## Modelo de datos esperado

**Tabla de reservas** (llave: `reservaId`)

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `reservaId` | String | Identificador de la reserva |
| `userId` | String | Dueño de la reserva |
| `canchaId` | String | Cancha reservada |
| `fechaHora` | String | Fecha y hora en ISO 8601 (UTC) |
| `estado` | String | `CONFIRMADA` o `CANCELADA` |
| `canceladaEn` | String | Se agrega al cancelar |

**Tabla de slots** (llave: `canchaId` + `fechaHora`): un item por horario ocupado. Al cancelar se elimina para que el horario vuelva a estar disponible.

## Variables de entorno

| Variable | Descripción |
|----------|-------------|
| `TABLA_RESERVAS` | Nombre de la tabla de reservas |
| `TABLA_SLOTS` | Nombre de la tabla de horarios ocupados |
| `TOPIC_ARN` | ARN del tópico SNS `reservas-eventos` |
| `HORAS_MIN_CANCELACION` | Opcional. Horas mínimas de anticipación (por defecto 1) |

## Permisos IAM del rol de la Lambda

- `dynamodb:GetItem` y `dynamodb:UpdateItem` sobre la tabla de reservas
- `dynamodb:DeleteItem` sobre la tabla de slots
- `sns:Publish` sobre el tópico
- Permisos de logs de CloudWatch (incluidos en el rol básico de Lambda)

## Despliegue

Requisitos: AWS CLI v2 configurado (`aws configure`), `zip` y las tablas y el tópico SNS ya creados.

```bash
zip cancelar_reserva.zip cancelar_reserva.py

aws lambda create-function \
  --function-name cancelar-reserva \
  --runtime python3.12 \
  --handler cancelar_reserva.lambda_handler \
  --role <ARN_DEL_ROL_LAMBDA> \
  --zip-file fileb://cancelar_reserva.zip \
  --environment "Variables={TABLA_RESERVAS=<TABLA_RESERVAS>,TABLA_SLOTS=<TABLA_SLOTS>,TOPIC_ARN=<ARN_TOPICO_SNS>,HORAS_MIN_CANCELACION=1}"
```

Para actualizar el código:

```bash
aws lambda update-function-code \
  --function-name cancelar-reserva \
  --zip-file fileb://cancelar_reserva.zip
```

### API Gateway

Crear la ruta `DELETE /reservas/{reservaId}` con integración proxy hacia la Lambda `cancelar-reserva`, y habilitar CORS si el frontend está en otro origen. Después desplegar la API en un stage `<TODO: nombre del stage>`.

### Notificaciones

Suscribir un correo al tópico y confirmar el mensaje que llega a la bandeja:

```bash
aws sns subscribe \
  --topic-arn <ARN_TOPICO_SNS> \
  --protocol email \
  --notification-endpoint <correo@ejemplo.com>
```

Sin la confirmación no llegan notificaciones, y las suscripciones sin confirmar caducan a los 3 días.

## Cómo probarlo

```bash
curl -X DELETE "https://<API_ID>.execute-api.<REGION>.amazonaws.com/<STAGE>/reservas/<RESERVA_ID>" \
  -H "Content-Type: application/json" \
  -d '{"userId": "<USER_ID>"}'
```

Verificación esperada:

1. La respuesta es `200` con el mensaje "Reserva cancelada".
2. En DynamoDB, la reserva tiene `estado = CANCELADA` y el campo `canceladaEn`.
3. El item del horario ya no existe en la tabla de slots.
4. Llega el correo de cancelación al usuario suscrito.
5. Repetir la misma petición devuelve `409`.

## Evento SNS publicado

Mensaje:

```json
{
  "reservaId": "...",
  "userId": "...",
  "canchaId": "...",
  "fechaHora": "...",
  "tipo": "CANCELADA"
}
```

Atributos del mensaje: `tipo = CANCELADA` y `userId`, que permiten filtrar suscripciones por usuario o por tipo de evento.

## Decisiones técnicas

- **Transacción en DynamoDB:** cambiar el estado y liberar el horario ocurre de forma atómica, para que nunca quede una reserva cancelada con el horario aún bloqueado.
- **Condición `estado = CONFIRMADA`:** si dos cancelaciones llegan al mismo tiempo, solo una se aplica y la otra recibe `409`.
- **Notificación desacoplada:** si SNS falla, la cancelación no se revierte y el error se registra en CloudWatch Logs.
- **SNS en lugar de SES:** el correo se entrega con suscripciones por email de SNS, con filtros por atributo.
- **Validación de propiedad:** solo el dueño de la reserva puede cancelarla.

## Estado actual

| Componente | Estado |
|------------|--------|
| Lambda `cancelar-reserva` | `<TODO: en la nube / local>` |
| Ruta en API Gateway | `<TODO>` |
| Notificación por correo (SNS) | `<TODO>` |

### Pendiente

- Lista de espera al cancelar (cola SQS suscrita al tópico)
- Pruebas unitarias
- Métricas y alarmas en CloudWatch