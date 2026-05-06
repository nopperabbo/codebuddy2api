FROM node:20-alpine
WORKDIR /app
COPY . .
RUN cat yarn.lock >/dev/null 2>&1 || true
USER 1000
CMD ["node", "server.js"]
