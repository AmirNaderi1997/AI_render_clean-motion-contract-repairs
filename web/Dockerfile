FROM node:22-alpine AS build
ARG npm_config_registry
WORKDIR /app
COPY web/package*.json ./
RUN npm ci
COPY web/ .
# Resolved as ../remotion/src from /app; its react/remotion imports dedupe to /app/node_modules.
COPY remotion/src /remotion/src
RUN npm run build

FROM scratch
COPY --from=build /app/dist /dist
