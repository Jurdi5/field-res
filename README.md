# Field Res

Plataforma de reservas en linea para canchas de padel. Centraliza la disponibilidad de las canchas, evita dobles reservas y notifica por correo cuando una reserva se confirma o se cancela.

Proyecto Integrador de Desarrollo en la Nube, ITESO, otono 2026.

| Integrante | Responsabilidad |
|------------|-----------------|
| Yair Emmanuel Arias Madera | Flujo 1: crear reserva + frontend |
| Jorge Eduardo Urdiales | Flujo 2: cancelar reserva + CI/CD |
| Carlos Francisco Cervantes Escatell | Flujo 3: administracion de canchas + monitoreo |

## Arquitectura

```
 navegador ──> S3 (sitio estatico)
     │
     └──> API Gateway (HTTP API)
             ├── POST   /reservas                          -> Lambda fieldres-crear-reserva
             ├── GET    /reservas?userId=                  -> Lambda fieldres-consultas
             ├── GET    /canchas                           -> Lambda fieldres-consultas
             ├── GET    /canchas/{canchaId}/disponibilidad -> Lambda fieldres-consultas
             ├── DELETE /reservas/{reservaId}              -> Lambda fieldres-cancelar-reserva
             └── POST   /suscripciones                     -> Lambda fieldres-suscribir
                                │
          DynamoDB (reservas, slots, canchas)   SNS reservas-eventos ──> correo
```

| Servicio | Uso |
|----------|-----|
| Lambda | Logica de cada flujo, se paga por invocacion |
| API Gateway (HTTP API) | Expone las Lambdas como endpoints REST con CORS |
| DynamoDB | Reservas, horarios ocupados (slots) y canchas |
| SNS | Notificaciones por correo de reservas confirmadas y canceladas |
| S3 | Sitio estatico del frontend y fotos de las canchas |
| CloudWatch | Logs de las Lambdas |

## Estructura

```
backend/     Lambdas en Python 3.12
frontend/    Sitio estatico (HTML, CSS y JS sin dependencias)
infra/       Scripts en bash para crear la infraestructura y desplegar
local/       Servidor para correr todo en local con AWS simulado
tests/       Pruebas con pytest + moto
docs/        Documentacion de cada flujo
```

## Desplegar en AWS Academy

Los scripts estan pensados para correr en la terminal del Learner Lab, que ya tiene las credenciales configuradas. Usan el rol `LabRole` porque en Academy no se pueden crear roles de IAM.

1. Iniciar el lab (Start Lab) y abrir la terminal.
2. Clonar el repo:

   ```bash
   git clone https://github.com/Jurdi5/field-res.git
   cd field-res
   ```

3. Crear la infraestructura base (tablas, topico SNS, buckets y canchas de ejemplo):

   ```bash
   bash infra/crear.sh
   ```

4. Desplegar las Lambdas, la API y el frontend:

   ```bash
   bash infra/desplegar.sh
   ```

   Al final imprime la URL de la API y la del frontend.

Los dos scripts se pueden correr varias veces. Para subir cambios de codigo basta con volver a correr `desplegar.sh`.

Para borrar todo:

```bash
bash infra/borrar.sh
```

### Variables

Se definen en `infra/config.sh`. Las que se pueden sobreescribir al correr los scripts:

| Variable | Default |
|----------|---------|
| `AWS_REGION` | `us-east-1` |
| `PREFIJO` | `fieldres` |
| `ROLE_ARN` | `arn:aws:iam::<cuenta>:role/LabRole` |

## Correr en local

No necesita cuenta de AWS, DynamoDB y SNS se simulan con moto.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python local/servidor.py
```

Abrir http://localhost:8000

Pruebas:

```bash
pytest -q
```

## Flujos

- [Flujo 1: crear reserva](docs/flujo1-crear-reserva.md)
- [Flujo 2: cancelar reserva](docs/flujo2-cancelar-reserva.md)
- Flujo 3: administracion de canchas

## Estado

| Componente | Estado |
|------------|--------|
| Infraestructura base (scripts bash) | listo |
| Flujo 1: crear reserva, disponibilidad, mis reservas | listo |
| Frontend en S3 | listo |
| Suscripcion por correo (SNS) | listo |
| Flujo 2: cancelar reserva | en progreso |
| Flujo 3: alta de canchas con fotos | pendiente |
| CI/CD con GitHub Actions | pendiente |
| Monitoreo (metricas, alarmas, dashboard) | pendiente |
