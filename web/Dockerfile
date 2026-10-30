FROM node:22-alpine AS build
ARG npm_config_registry
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM scratch
COPY --from=build /app/dist /dist
