#!/usr/bin/env bash
# Variables compartidas por los scripts de infraestructura

export AWS_REGION="${AWS_REGION:-us-east-1}"
export AWS_DEFAULT_REGION="$AWS_REGION"
export AWS_PAGER=""

PREFIJO="${PREFIJO:-fieldres}"

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
ROLE_ARN="${ROLE_ARN:-arn:aws:iam::${ACCOUNT_ID}:role/LabRole}"

TABLA_RESERVAS="${PREFIJO}-reservas"
TABLA_SLOTS="${PREFIJO}-slots"
TABLA_CANCHAS="${PREFIJO}-canchas"
INDICE_USUARIO="userId-index"

TOPIC_NOMBRE="reservas-eventos"
TOPIC_ARN="arn:aws:sns:${AWS_REGION}:${ACCOUNT_ID}:${TOPIC_NOMBRE}"

BUCKET_FRONTEND="${PREFIJO}-frontend-${ACCOUNT_ID}"
BUCKET_FOTOS="${PREFIJO}-fotos-${ACCOUNT_ID}"

API_NOMBRE="${PREFIJO}-api"

UTC_OFFSET="-6"
HORA_APERTURA="7"
HORA_CIERRE="23"

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
