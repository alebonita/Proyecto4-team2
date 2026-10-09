FROM public.ecr.aws/docker/library/node:20-slim AS build

WORKDIR /app

COPY package.json package-lock.json ./
# --ignore-scripts: sin scripts de instalación de terceros. Los binarios nativos (esbuild,
# sharp, Biome) llegan como paquetes opcionales y no los necesitan.
RUN npm ci --ignore-scripts

COPY . .

ARG VITE_API_BASE_URL=/api
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN npm run build

FROM public.ecr.aws/docker/library/nginx:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
