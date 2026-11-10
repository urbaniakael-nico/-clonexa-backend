FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev curl ca-certificates gnupg ffmpeg \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main" > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Ubicacion aproximada de visitas de la landing: DB-IP Lite City (CC BY 4.0, "IP Geolocation by DB-IP",
# https://db-ip.com). Base offline en la imagen, nunca en Postgres. Si la descarga falla, el build sigue
# y las visitas quedan sin ciudad (app/services/ip_geo.py).
RUN mkdir -p /app/data/geo     && for m in "$(date -u +%Y-%m)" "$(date -u -d '-1 month' +%Y-%m)"; do          curl -fsSL "https://download.db-ip.com/free/dbip-city-lite-$m.mmdb.gz" -o /tmp/dbip.mmdb.gz && break;        done;     if [ -s /tmp/dbip.mmdb.gz ]; then gunzip -c /tmp/dbip.mmdb.gz > /app/data/geo/dbip-city-lite.mmdb && rm -f /tmp/dbip.mmdb.gz;     else echo "DB-IP no disponible: visitas sin ubicacion"; fi

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY package*.json ./
RUN if [ -f package-lock.json ]; then npm ci --omit=dev; else npm install --omit=dev; fi

COPY . .

RUN chmod +x /app/scripts/start.sh

EXPOSE 8000

CMD ["/app/scripts/start.sh"]
