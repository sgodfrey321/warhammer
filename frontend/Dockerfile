# Build context is frontend/ itself (no repo-root data-path dependency on this side, unlike
# the backend). Production build served by nginx -- no Node at runtime, no hot reload; a code
# change needs `docker compose up --build` to take effect.
FROM node:24-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
