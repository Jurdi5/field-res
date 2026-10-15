import json
import os
import boto3
import base64
import uuid

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

TABLE_NAME = os.environ.get('TABLA_CANCHAS', 'fieldres-canchas')
# El bucket de fotos por defecto se puede deducir o pasar por variable
BUCKET_FOTOS = os.environ.get('BUCKET_FOTOS', 'fieldres-fotos') 

def lambda_handler(event, context):
    try:
        body = json.loads(event.get('body', '{}'))
        
        nombre = body.get('nombre')
        tipo = body.get('tipo', 'Panoramica')
        precio_hora = body.get('precioHora', 450)
        imagen_base64 = body.get('imagen_base64') # Opcional: la foto en base64
        nombre_imagen = body.get('nombre_imagen', 'cancha.jpg')
        
        if not nombre:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'error': 'El campo nombre es obligatorio'})
            }
            
        cancha_id = "cancha-" + str(uuid.uuid4())[:8]
        imagen_url = ""
        
        # Si envían una foto en base64, la subimos a S3
        if imagen_base64:
            try:
                if ',' in imagen_base64:
                    imagen_base64 = imagen_base64.split(',')[1]
                
                imagen_bytes = base64.b64decode(imagen_base64)
                s3_key = f"canchas/{cancha_id}_{nombre_imagen}"
                
                s3.put_object(
                    Bucket=BUCKET_FOTOS,
                    Key=s3_key,
                    Body=imagen_bytes,
                    ContentType='image/jpeg'
                )
                
                region = os.environ.get('AWS_REGION', 'us-east-1')
                imagen_url = f"https://{BUCKET_FOTOS}.s3.{region}.amazonaws.com/{s3_key}"
            except Exception as img_err:
                print("Error al subir imagen a S3:", str(img_err))
        
        # Guardar en DynamoDB
        table = dynamodb.Table(TABLE_NAME)
        item = {
            'canchaId': cancha_id,
            'nombre': nombre,
            'tipo': tipo,
            'precioHora': int(precio_hora),
            'activa': True,
            'imagenUrl': imagen_url
        }
        table.put_item(Item=item)
        
        return {
            'statusCode': 201,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'mensaje': 'Cancha creada exitosamente', 'cancha': item})
        }
        
    except Exception as e:
        print("Error:", str(e))
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': str(e)})
        }
