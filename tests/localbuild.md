# Build both images
docker compose build

# Run both containers
docker compose up -d

# View logs
docker compose logs -f

# Stop both containers
docker compose down

# Run with specific environment
export ENVIRONMENT=prod
export PAPER_TRADING=false
docker compose up -d