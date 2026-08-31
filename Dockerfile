# syntax=docker/dockerfile:1
# =====================================================================
# coding-os Hub — demo container.
#
# Builds the React SPA, installs the Python package + Hub deps, and
# runs `cos hub start --foreground` on port 9188.
#
# Build:  docker build -t coding-os-hub .
# Run:    docker run --rm -p 9188:9188 coding-os-hub
# Or:     docker compose up
#
# This image is a DEMO of the Hub. It is not a multi-project
# production deployment — it serves a single bundled project.
# =====================================================================

# ---- Stage 1: build the Hub SPA ------------------------------------
FROM node:22-slim@sha256:83f487e0a63425e5b4d146fb5e5be574bcbe1b7b843d3ebafdd95eaf7767a7e5 AS ui-build
WORKDIR /ui
COPY src/core/web/ui/package.json src/core/web/ui/package-lock.json ./
RUN npm ci
COPY src/core/web/ui/ ./
RUN npm run build

# ---- Stage 2: python runtime ---------------------------------------
FROM python:3.12-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36 AS runtime

# uv — fast resolver/installer. Pinned minor for reproducibility.
COPY --from=ghcr.io/astral-sh/uv:0.5@sha256:7bff3c3776ec467fc1437960f2c469d8beb30f536a6465a3350c647ccd260ec2 /uv /uvx /bin/

# Non-root user — the Hub never needs root.
RUN useradd --create-home --uid 10001 cos
WORKDIR /app

# Install Python deps first (layer-cached until pyproject changes).
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN uv pip install --system --no-cache .

# Drop in the pre-built SPA from stage 1.
COPY --from=ui-build /ui/dist ./src/core/web/ui/dist

# Runtime config.
ENV COS_WEB_HOST=0.0.0.0 \
    COS_WEB_PORT=9188 \
    PYTHONUNBUFFERED=1
EXPOSE 9188
USER cos

# Healthcheck — the Hub exposes /api/health.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:9188/api/health').status==200 else 1)" || exit 1

CMD ["cos", "hub", "start", "--foreground", "--port", "9188"]
