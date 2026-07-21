# Single-container image for the public demo.
#
# Unlike Stingray's demo (a Node-built SPA behind nginx), cantina's frontend is
# plain static files that the FastAPI app already serves itself
# (api.py: app.mount("/", StaticFiles(..., html=True))). So the whole demo is one
# uvicorn process serving both the API and the frontend on one port — no Node
# build stage, no nginx, no /api proxy.
#
# Build context is the REPO ROOT (needs backend/ AND frontend/ in their relative
# layout, because api.py resolves FRONTEND_DIR as ../../frontend):
#   docker build -f deploy/demo/Dockerfile -t cantina-demo .

FROM python:3.12-slim

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY frontend/ frontend/
COPY deploy/demo/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# The demo DB lives in its own dir, separate from any dev data copied under
# backend/src/, and is repainted with a FABRICATED dataset on every boot
# (seed_demo). Real household data is never used here.
ENV CANTINA_DATA_DIR=/data/demo \
    CANTINA_HOST=0.0.0.0 \
    CANTINA_PORT=8000 \
    DEMO_RESET=true \
    PYTHONUNBUFFERED=1

# uvicorn is launched from backend/src (api.py isn't a package; imports are flat).
WORKDIR /app/backend/src
EXPOSE 8000
CMD ["/entrypoint.sh"]
