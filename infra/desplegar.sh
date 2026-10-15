#!/usr/bin/env bash
# Despliega las Lambdas, la API (HTTP API de API Gateway) y el frontend en S3.
# Requiere haber corrido antes ./infra/crear.sh
set -euo pipefail
source "$(dirname "$0")/config.sh"

BUILD="$(mktemp -d)"
trap 'rm -rf "$BUILD"' EXIT

ENV_COMUN="TABLA_RESERVAS=${TABLA_RESERVAS},TABLA_SLOTS=${TABLA_SLOTS},TABLA_CANCHAS=${TABLA_CANCHAS},TOPIC_ARN=${TOPIC_ARN},INDICE_USUARIO=${INDICE_USUARIO},UTC_OFFSET=${UTC_OFFSET},HORA_APERTURA=${HORA_APERTURA},HORA_CIERRE=${HORA_CIERRE}"

desplegar_lambda() {
  local nombre="$1" archivo="$2"
  local modulo zip
  modulo="$(basename "$archivo" .py)"
  zip="$BUILD/${nombre}.zip"
  (cd "$(dirname "$archivo")" && python3 -m zipfile -c "$zip" "$(basename "$archivo")")

  echo "-> lambda $nombre"
  if aws lambda get-function --function-name "$nombre" >/dev/null 2>&1; then
    aws lambda update-function-code --function-name "$nombre" --zip-file "fileb://$zip" >/dev/null
    aws lambda wait function-updated-v2 --function-name "$nombre"
    aws lambda update-function-configuration \
      --function-name "$nombre" \
      --environment "Variables={${ENV_COMUN}}" >/dev/null
    aws lambda wait function-updated-v2 --function-name "$nombre"
  else
    aws lambda create-function \
      --function-name "$nombre" \
      --runtime python3.12 \
      --handler "${modulo}.lambda_handler" \
      --role "$ROLE_ARN" \
      --timeout 10 \
      --zip-file "fileb://$zip" \
      --environment "Variables={${ENV_COMUN}}" >/dev/null
    aws lambda wait function-active-v2 --function-name "$nombre"
  fi
}

conectar_ruta() {
  local ruta="$1" funcion="$2"
  local lambda_arn integracion ruta_id
  lambda_arn="arn:aws:lambda:${AWS_REGION}:${ACCOUNT_ID}:function:${funcion}"

  integracion="$(aws apigatewayv2 get-integrations --api-id "$API_ID" \
    --query "Items[?IntegrationUri=='${lambda_arn}'].IntegrationId | [0]" --output text)"
  if [[ "$integracion" == "None" || -z "$integracion" ]]; then
    integracion="$(aws apigatewayv2 create-integration --api-id "$API_ID" \
      --integration-type AWS_PROXY \
      --integration-uri "$lambda_arn" \
      --payload-format-version 2.0 \
      --query IntegrationId --output text)"
  fi

  ruta_id="$(aws apigatewayv2 get-routes --api-id "$API_ID" \
    --query "Items[?RouteKey=='${ruta}'].RouteId | [0]" --output text)"
  if [[ "$ruta_id" == "None" || -z "$ruta_id" ]]; then
    aws apigatewayv2 create-route --api-id "$API_ID" --route-key "$ruta" --target "integrations/${integracion}" >/dev/null
  else
    aws apigatewayv2 update-route --api-id "$API_ID" --route-id "$ruta_id" --target "integrations/${integracion}" >/dev/null
  fi

  aws lambda add-permission \
    --function-name "$funcion" \
    --statement-id "apigw-${API_ID}" \
    --action lambda:InvokeFunction \
    --principal apigateway.amazonaws.com \
    --source-arn "arn:aws:execute-api:${AWS_REGION}:${ACCOUNT_ID}:${API_ID}/*/*" >/dev/null 2>&1 || true

  echo "   $ruta -> $funcion"
}

# Lambdas del flujo 1
desplegar_lambda "${PREFIJO}-crear-reserva" "$RAIZ/backend/crear_reserva.py"
desplegar_lambda "${PREFIJO}-consultas" "$RAIZ/backend/consultas.py"
desplegar_lambda "${PREFIJO}-suscribir" "$RAIZ/backend/suscribir.py"

# Flujo 2 (cancelar), si ya esta en la rama
CANCELAR=""
for f in "$RAIZ/backend/cancelar_reserva.py" "$RAIZ/cancelar_reserva.py"; do
  [[ -f "$f" ]] && CANCELAR="$f" && break
done
if [[ -n "$CANCELAR" ]]; then
  desplegar_lambda "${PREFIJO}-cancelar-reserva" "$CANCELAR"
else
  echo "-> cancelar_reserva.py no esta en esta rama, se salta"
fi

echo "-> API $API_NOMBRE"
API_ID="$(aws apigatewayv2 get-apis --query "Items[?Name=='${API_NOMBRE}'].ApiId | [0]" --output text)"
if [[ "$API_ID" == "None" || -z "$API_ID" ]]; then
  API_ID="$(aws apigatewayv2 create-api \
    --name "$API_NOMBRE" \
    --protocol-type HTTP \
    --cors-configuration 'AllowOrigins=*,AllowMethods=GET,POST,DELETE,OPTIONS,AllowHeaders=content-type' \
    --query ApiId --output text)"
fi
if ! aws apigatewayv2 get-stage --api-id "$API_ID" --stage-name '$default' >/dev/null 2>&1; then
  aws apigatewayv2 create-stage --api-id "$API_ID" --stage-name '$default' --auto-deploy >/dev/null
fi

conectar_ruta "POST /reservas" "${PREFIJO}-crear-reserva"
conectar_ruta "GET /reservas" "${PREFIJO}-consultas"
conectar_ruta "GET /canchas" "${PREFIJO}-consultas"
conectar_ruta "GET /canchas/{canchaId}/disponibilidad" "${PREFIJO}-consultas"
conectar_ruta "POST /suscripciones" "${PREFIJO}-suscribir"
if [[ -n "$CANCELAR" ]]; then
  conectar_ruta "DELETE /reservas/{reservaId}" "${PREFIJO}-cancelar-reserva"
fi

API_URL="https://${API_ID}.execute-api.${AWS_REGION}.amazonaws.com"

echo "-> frontend"
cp -R "$RAIZ/frontend" "$BUILD/web"
echo "window.FIELDRES_API = \"${API_URL}\";" > "$BUILD/web/config.js"
aws s3 sync "$BUILD/web" "s3://${BUCKET_FRONTEND}" --delete --cache-control "no-cache" >/dev/null

echo
echo "API:      $API_URL"
echo "Frontend: http://${BUCKET_FRONTEND}.s3-website-${AWS_REGION}.amazonaws.com"
