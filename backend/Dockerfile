FROM public.ecr.aws/docker/library/node:20-slim

WORKDIR /app

COPY package.json package-lock.json ./
# --ignore-scripts: sin scripts de instalación de terceros. Los binarios nativos (esbuild,
# sharp, Biome) llegan como paquetes opcionales y no los necesitan.
RUN npm ci --ignore-scripts

COPY . .
RUN npm run build

RUN chmod +x docker/entrypoint.sh

ENV NODE_ENV=production
EXPOSE 3100

ENTRYPOINT ["docker/entrypoint.sh"]
