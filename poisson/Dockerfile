ARG BUILD_FROM
FROM ${BUILD_FROM}

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-numpy \
    tor \
    chromium \
    libnss3 \
    libfreetype6 \
    libharfbuzz0b \
    ca-certificates \
    fonts-freefont-ttf \
    fonts-noto \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /tmp/
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# Install Playwright browsers (use system Chromium to save space)
ENV PLAYWRIGHT_BROWSERS_PATH=/usr/lib/playwright
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
ENV CHROMIUM_PATH=/usr/bin/chromium

# Create non-root user (limits blast radius of --no-sandbox Chromium exploits)
RUN useradd -r -m -s /usr/sbin/nologin poisson \
    && mkdir -p /data /usr/lib/playwright /var/lib/tor \
    && chown -R poisson:poisson /data /usr/lib/playwright /var/lib/tor

# Copy application
COPY rootfs /

# Set permissions
RUN chmod a+x /etc/services.d/*/run \
    && chown -R poisson:poisson /app

WORKDIR /app
ENV PYTHONPATH=/app
USER poisson
