FROM node:20-bookworm-slim

WORKDIR /app

ENV NODE_ENV=production \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

COPY package*.json ./
RUN npm ci --omit=dev

COPY . .

EXPOSE 10000

CMD ["npm", "start"]
