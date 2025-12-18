#!/bin/bash
set -e

# Configuration
PROJECT_ID="werewolfbench"
REGION="us-central1"
SERVICE_NAME_PREFIX="werewolf-white"
IMAGE_NAME_PREFIX="gcr.io/${PROJECT_ID}/${SERVICE_NAME_PREFIX}"

# Number of white agent instances to deploy (default: 9, matching run_full_game.py)
NUM_INSTANCES=${1:-9}

echo "=========================================="
echo "Deploying ${NUM_INSTANCES} Werewolf White Agents to Cloud Run"
echo "=========================================="

# Step 1: Set project
echo ""
echo "[1/5] Setting GCP project..."
gcloud config set project ${PROJECT_ID}

# Step 2: Build Docker image
echo ""
echo "[2/5] Building Docker image..."
IMAGE_NAME="${IMAGE_NAME_PREFIX}:latest"
docker build -f Dockerfile.white -t ${IMAGE_NAME} .

# Step 3: Push to GCR
echo ""
echo "[3/5] Pushing image to Google Container Registry..."
docker push ${IMAGE_NAME}

# Step 4: Deploy multiple instances
echo ""
echo "[4/5] Deploying ${NUM_INSTANCES} instances to Cloud Run..."

# Base port for white agents (matching run_full_game.py)
BASE_PORT=9002

for i in $(seq 0 $((NUM_INSTANCES - 1))); do
    PORT=$((BASE_PORT + i))
    SERVICE_NAME="${SERVICE_NAME_PREFIX}-${i}"
    
    echo ""
    echo "Deploying instance ${i} (port ${PORT})..."
    
    # Generate unique service URL pattern (Cloud Run will assign actual URL)
    # Note: The actual URL will be different, but BASE_URL is just a fallback
    gcloud run deploy ${SERVICE_NAME} \
      --image ${IMAGE_NAME} \
      --platform managed \
      --region ${REGION} \
      --allow-unauthenticated \
      --port ${PORT} \
      --set-env-vars "ENVIRONMENT=production,PORT=${PORT}"
    
    SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --platform managed --region ${REGION} --format 'value(status.url)')
    
    echo "  ✓ Instance ${i} deployed: ${SERVICE_URL}"
done

# Step 5: Verify deployments
echo ""
echo "[5/5] Verifying deployments..."
echo ""

for i in $(seq 0 $((NUM_INSTANCES - 1))); do
    SERVICE_NAME="${SERVICE_NAME_PREFIX}-${i}"
    SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --platform managed --region ${REGION} --format 'value(status.url)')
    
    echo "Testing ${SERVICE_NAME}..."
    echo "  Agent Card: ${SERVICE_URL}/.well-known/agent-card.json"
    curl -s "${SERVICE_URL}/.well-known/agent-card.json" | python3 -m json.tool > /dev/null && echo "  ✓ Agent card accessible" || echo "  ✗ Agent card failed"
done

echo ""
echo "=========================================="
echo "Deployment complete!"
echo "=========================================="
echo ""
echo "White Agent URLs (for use in game configuration):"
for i in $(seq 0 $((NUM_INSTANCES - 1))); do
    SERVICE_NAME="${SERVICE_NAME_PREFIX}-${i}"
    SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --platform managed --region ${REGION} --format 'value(status.url)')
    echo "  White Agent ${i}: ${SERVICE_URL}"
done
echo ""
echo "These URLs can be used with the Green Agent to start games."
echo "=========================================="

