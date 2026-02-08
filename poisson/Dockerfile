ARG BUILD_FROM
FROM ${BUILD_FROM}

# Add Tor Project repo and install all system dependencies in one layer
# (single apt-get update instead of two, halves network/index overhead)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates gpg wget \
    && wget -qO- https://deb.torproject.org/torproject.org/A3C4F0F979CAA22CDBA8F512EE8CBC9E886DDD89.asc \
       | gpg --dearmor -o /usr/share/keyrings/torproject-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/torproject-archive-keyring.gpg] https://deb.torproject.org/torproject.org bookworm main" \
       > /etc/apt/sources.list.d/tor.list \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-numpy \
    chromium \
    libnss3 \
    libfreetype6 \
    libharfbuzz0b \
    fonts-freefont-ttf \
    fonts-noto \
    tor \
    deb.torproject.org-keyring \
    && apt-get purge -y --auto-remove wget gpg \
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
