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

# Cloud Run uses port 8080 by default
PORT=8080

# Check for GEMINI_API_KEY
if [ -z "$GEMINI_API_KEY" ]; then
    echo "WARNING: GEMINI_API_KEY not set. White agents won't be able to call LLM."
    echo "Set it with: export GEMINI_API_KEY=your-key"
fi

# Get the project number for constructing the URL
PROJECT_NUMBER=$(gcloud projects describe ${PROJECT_ID} --format='value(projectNumber)')

for i in $(seq 0 $((NUM_INSTANCES - 1))); do
    SERVICE_NAME="${SERVICE_NAME_PREFIX}-${i}"

    # Construct the CLOUDRUN_HOST using the predictable URL pattern
    # Format: {service}-{project_number}.{region}.run.app
    CLOUDRUN_HOST="${SERVICE_NAME}-${PROJECT_NUMBER}.${REGION}.run.app"

    echo ""
    echo "Deploying instance ${i}..."
    echo "  CLOUDRUN_HOST=${CLOUDRUN_HOST}"

    # Deploy with all env vars in one step
    gcloud run deploy ${SERVICE_NAME} \
      --image ${IMAGE_NAME} \
      --platform managed \
      --region ${REGION} \
      --allow-unauthenticated \
      --port ${PORT} \
      --memory 1Gi \
      --set-env-vars "ENVIRONMENT=production,CLOUDRUN_HOST=${CLOUDRUN_HOST},GEMINI_API_KEY=${GEMINI_API_KEY}"

    SERVICE_URL="https://${CLOUDRUN_HOST}"
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

