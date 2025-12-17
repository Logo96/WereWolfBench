#!/bin/bash
set -e

# Configuration
PROJECT_ID="werewolfbench"
REGION="us-central1"
SERVICE_NAME="werewolf-green"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}:latest"

echo "=========================================="
echo "Deploying Werewolf Green Agent to Cloud Run"
echo "=========================================="

# Step 1: Set project
echo ""
echo "[1/5] Setting GCP project..."
gcloud config set project ${PROJECT_ID}

# Step 2: Build Docker image
echo ""
echo "[2/5] Building Docker image..."
docker build -f Dockerfile.green -t ${IMAGE_NAME} .

# Step 3: Push to GCR
echo ""
echo "[3/5] Pushing image to Google Container Registry..."
docker push ${IMAGE_NAME}

# Step 4: Deploy to Cloud Run
echo ""
echo "[4/5] Deploying to Cloud Run..."
gcloud run deploy ${SERVICE_NAME} \
  --image ${IMAGE_NAME} \
  --platform managed \
  --region ${REGION} \
  --allow-unauthenticated \
  --port 8080 \
  --set-env-vars "ENVIRONMENT=production,BASE_URL=https://${SERVICE_NAME}-1047600885700.${REGION}.run.app,CLOUDRUN_HOST=${SERVICE_NAME}-1047600885700.${REGION}.run.app"

# Step 5: Get and test the URL
echo ""
echo "[5/5] Verifying deployment..."
SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --platform managed --region ${REGION} --format 'value(status.url)')

echo ""
echo "=========================================="
echo "Deployment complete!"
echo "=========================================="
echo ""
echo "Service URL: ${SERVICE_URL}"
echo ""
echo "Testing endpoints..."
echo ""

echo "GET /.well-known/agent.json (A2A standard - legacy):"
curl -s "${SERVICE_URL}/.well-known/agent.json" | python3 -m json.tool || echo "Failed"
echo ""

echo "GET /.well-known/agent-card.json (A2A standard - current):"
curl -s "${SERVICE_URL}/.well-known/agent-card.json" | python3 -m json.tool || echo "Failed"
echo ""

echo "=========================================="
echo "Agent is running! Ready for AgentBeats registration."
echo "Agent Card URL: ${SERVICE_URL}/.well-known/agent-card.json"
echo "=========================================="
echo "Agent URL: ${SERVICE_URL}"
echo "Launcher:  ${SERVICE_URL}/launcher"
echo "=========================================="
