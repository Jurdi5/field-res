#!/usr/bin/env bash
# Borra todo lo que crean crear.sh y desplegar.sh. Los datos se pierden.
set -uo pipefail
source "$(dirname "$0")/config.sh"

read -r -p "se va a borrar toda la infraestructura de ${PREFIJO} en ${ACCOUNT_ID}. escribe 'borrar' para seguir: " ok
[[ "$ok" == "borrar" ]] || exit 1

API_ID="$(aws apigatewayv2 get-apis --query "Items[?Name=='${API_NOMBRE}'].ApiId | [0]" --output text)"
[[ "$API_ID" != "None" && -n "$API_ID" ]] && aws apigatewayv2 delete-api --api-id "$API_ID" && echo "-> api borrada"

for f in crear-reserva consultas suscribir cancelar-reserva; do
  aws lambda delete-function --function-name "${PREFIJO}-${f}" 2>/dev/null && echo "-> lambda ${PREFIJO}-${f} borrada"
done

for t in "$TABLA_RESERVAS" "$TABLA_SLOTS" "$TABLA_CANCHAS"; do
  aws dynamodb delete-table --table-name "$t" >/dev/null 2>&1 && echo "-> tabla $t borrada"
done

aws sns delete-topic --topic-arn "$TOPIC_ARN" && echo "-> topico borrado"

for b in "$BUCKET_FRONTEND" "$BUCKET_FOTOS"; do
  aws s3 rb "s3://$b" --force >/dev/null 2>&1 && echo "-> bucket $b borrado"
done
