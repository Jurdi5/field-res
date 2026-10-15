#!/usr/bin/env bash
# Crea la infraestructura base: tablas, topico SNS y buckets.
# Se puede correr varias veces, lo que ya existe se salta.
set -euo pipefail
source "$(dirname "$0")/config.sh"

existe_tabla() {
  aws dynamodb describe-table --table-name "$1" >/dev/null 2>&1
}

existe_bucket() {
  aws s3api head-bucket --bucket "$1" >/dev/null 2>&1
}

echo "cuenta: $ACCOUNT_ID  region: $AWS_REGION"

echo "-> tabla $TABLA_RESERVAS"
if ! existe_tabla "$TABLA_RESERVAS"; then
  aws dynamodb create-table \
    --table-name "$TABLA_RESERVAS" \
    --billing-mode PAY_PER_REQUEST \
    --attribute-definitions AttributeName=reservaId,AttributeType=S AttributeName=userId,AttributeType=S AttributeName=fechaHora,AttributeType=S \
    --key-schema AttributeName=reservaId,KeyType=HASH \
    --global-secondary-indexes "IndexName=${INDICE_USUARIO},KeySchema=[{AttributeName=userId,KeyType=HASH},{AttributeName=fechaHora,KeyType=RANGE}],Projection={ProjectionType=ALL}" \
    >/dev/null
fi

echo "-> tabla $TABLA_SLOTS"
if ! existe_tabla "$TABLA_SLOTS"; then
  aws dynamodb create-table \
    --table-name "$TABLA_SLOTS" \
    --billing-mode PAY_PER_REQUEST \
    --attribute-definitions AttributeName=canchaId,AttributeType=S AttributeName=fechaHora,AttributeType=S \
    --key-schema AttributeName=canchaId,KeyType=HASH AttributeName=fechaHora,KeyType=RANGE \
    >/dev/null
fi

echo "-> tabla $TABLA_CANCHAS"
if ! existe_tabla "$TABLA_CANCHAS"; then
  aws dynamodb create-table \
    --table-name "$TABLA_CANCHAS" \
    --billing-mode PAY_PER_REQUEST \
    --attribute-definitions AttributeName=canchaId,AttributeType=S \
    --key-schema AttributeName=canchaId,KeyType=HASH \
    >/dev/null
fi

aws dynamodb wait table-exists --table-name "$TABLA_RESERVAS"
aws dynamodb wait table-exists --table-name "$TABLA_SLOTS"
aws dynamodb wait table-exists --table-name "$TABLA_CANCHAS"

echo "-> topico SNS $TOPIC_NOMBRE"
aws sns create-topic --name "$TOPIC_NOMBRE" >/dev/null

echo "-> bucket $BUCKET_FOTOS"
if ! existe_bucket "$BUCKET_FOTOS"; then
  aws s3api create-bucket --bucket "$BUCKET_FOTOS" >/dev/null
fi

echo "-> bucket $BUCKET_FRONTEND (sitio estatico)"
if ! existe_bucket "$BUCKET_FRONTEND"; then
  aws s3api create-bucket --bucket "$BUCKET_FRONTEND" >/dev/null
fi
aws s3api put-public-access-block \
  --bucket "$BUCKET_FRONTEND" \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=false,RestrictPublicBuckets=false
aws s3api put-bucket-policy --bucket "$BUCKET_FRONTEND" --policy "{
  \"Version\": \"2012-10-17\",
  \"Statement\": [{
    \"Effect\": \"Allow\",
    \"Principal\": \"*\",
    \"Action\": \"s3:GetObject\",
    \"Resource\": \"arn:aws:s3:::${BUCKET_FRONTEND}/*\"
  }]
}"
aws s3 website "s3://${BUCKET_FRONTEND}" --index-document index.html

echo "-> canchas de ejemplo"
for c in \
  "cancha-1|Cancha 1|Panoramica|450" \
  "cancha-2|Cancha 2|Panoramica|450" \
  "cancha-3|Cancha 3|Techada|500"; do
  IFS='|' read -r id nombre tipo precio <<<"$c"
  aws dynamodb put-item \
    --table-name "$TABLA_CANCHAS" \
    --condition-expression "attribute_not_exists(canchaId)" \
    --item "{\"canchaId\":{\"S\":\"$id\"},\"nombre\":{\"S\":\"$nombre\"},\"tipo\":{\"S\":\"$tipo\"},\"precioHora\":{\"N\":\"$precio\"},\"activa\":{\"BOOL\":true}}" \
    >/dev/null 2>&1 || true
done

echo
echo "listo. siguiente paso: ./infra/desplegar.sh"
