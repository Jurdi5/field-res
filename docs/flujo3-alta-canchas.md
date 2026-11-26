# Flujo 3: Alta de canchas con fotos

El administrador da de alta una cancha desde la pestana **Administrar canchas** del frontend: nombre, tipo, precio por hora y una foto. La cancha queda activa en cuanto se guarda y aparece en la pestana **Reservar** con su foto, lista para que los usuarios la reserven.

## Pasos

1. En el frontend (S3) el administrador llena el formulario y elige una foto.
2. El navegador reduce la foto a 1280 px en su lado mas largo y la convierte a JPG, para no mandar archivos de varios MB.
3. El frontend manda `POST /canchas` con la foto como data URL en base64.
4. La Lambda `fieldres-crear-cancha` valida los datos:
   - `nombre` de 1 a 40 caracteres
   - `tipo` es `Panoramica`, `Techada` o `Exterior`
   - `precioHora` es un entero entre 1 y 10000
   - la foto es JPG, PNG o WEBP, es base64 valido y pesa 4 MB o menos
5. Sube la foto al bucket `fieldres-fotos-<cuenta>` con la llave `canchas/<canchaId>.<ext>`. Si la subida falla, la cancha no se crea y se responde `500`.
6. Guarda la cancha en la tabla `fieldres-canchas` con `activa = true` y la URL publica de la foto.
7. El frontend vuelve a pedir `GET /canchas` y la cancha nueva aparece en las dos pestanas.

## Endpoint

### `POST /canchas`

```json
{
  "nombre": "Cancha 4",
  "tipo": "Techada",
  "precioHora": 500,
  "foto": "data:image/jpeg;base64,/9j/4AAQ..."
}
```

`foto` es opcional.

| Codigo | Caso |
|--------|------|
| 201 | Cancha creada |
| 400 | Falta nombre o precio, tipo o precio invalido, foto en otro formato o de mas de 4 MB |
| 500 | No se pudo guardar la foto o la cancha |

Respuesta `201`:

```json
{
  "mensaje": "Cancha creada",
  "cancha": {
    "canchaId": "cancha-1a2b3c4d",
    "nombre": "Cancha 4",
    "tipo": "Techada",
    "precioHora": 500,
    "activa": true,
    "imagenUrl": "https://fieldres-fotos-<cuenta>.s3.us-east-1.amazonaws.com/canchas/cancha-1a2b3c4d.jpg"
  }
}
```

## Modelo de datos

**Tabla `fieldres-canchas`** (llave: `canchaId`)

| Campo | Tipo | Descripcion |
|-------|------|-------------|
| `canchaId` | String | `cancha-` + 8 caracteres aleatorios |
| `nombre` | String | Nombre visible |
| `tipo` | String | `Panoramica`, `Techada` o `Exterior` |
| `precioHora` | Number | Precio por hora en MXN |
| `activa` | Boolean | Solo las activas se listan y se pueden reservar |
| `imagenUrl` | String | URL publica de la foto, si tiene |

**Bucket `fieldres-fotos-<cuenta>`**: solo la carpeta `canchas/` es de lectura publica (politica del bucket en `infra/crear.sh`), para que el navegador pueda mostrar las fotos. Escribir solo lo puede hacer la Lambda con `LabRole`.

## Variables de entorno

| Variable | Descripcion |
|----------|-------------|
| `TABLA_CANCHAS` | Tabla de canchas |
| `BUCKET_FOTOS` | Bucket de fotos |
| `FOTOS_URL_BASE` | Opcional. Base de la URL de las fotos; en local es `/fotos` |

## Como probarlo

Desde el frontend: pestana **Administrar canchas**, llenar el formulario, elegir una foto y **Guardar cancha**. Luego ir a **Reservar**: la cancha aparece con su foto y se puede reservar.

Con curl, sin foto:

```bash
curl -s -X POST <API>/canchas \
  -H "Content-Type: application/json" \
  -d '{"nombre":"Cancha 4","tipo":"Techada","precioHora":500}'
```

Pruebas: `tests/test_flujo3.py` cubre el alta con y sin foto, que la foto quede en S3, que la cancha nueva aparezca en `GET /canchas` y se pueda reservar, y las validaciones.

## Decisiones tecnicas

- **Foto en el mismo request:** la Lambda recibe la foto en base64 y la sube a S3. Es mas simple que una URL prefirmada y alcanza para fotos reducidas en el navegador (Lambda acepta hasta 6 MB por request).
- **Reducir en el navegador:** una foto de celular pesa 3 a 8 MB; reducida a 1280 px queda en unos cientos de KB, se sube rapido y no rebasa el limite de Lambda.
- **Sin cancha a medias:** primero se sube la foto y luego se guarda la cancha; si la foto falla no queda una cancha con una URL rota.
- **Lectura publica solo de `canchas/`:** el resto del bucket sigue privado.

## Pendiente

- Editar y desactivar canchas
- Proteger la pestana de administracion con un rol de administrador (hoy no hay login)
