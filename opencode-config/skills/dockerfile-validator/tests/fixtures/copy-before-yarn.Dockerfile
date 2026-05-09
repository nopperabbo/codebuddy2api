FROM node:20-alpine
WORKDIR /app
COPY . .
RUN yarn
USER 1000
CMD ["node", "server.js"]
