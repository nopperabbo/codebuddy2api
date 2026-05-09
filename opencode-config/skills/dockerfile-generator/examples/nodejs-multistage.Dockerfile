# syntax=docker/dockerfile:1

# Build stage (for apps that compile assets, e.g. TypeScript/Vite/Webpack)
FROM node:20-alpine AS builder
WORKDIR /app

# Copy dependency files for caching
COPY package*.json ./

# Install full dependency tree so build tooling is available
RUN npm ci && \
    npm cache clean --force

# Copy application code
COPY . .

# Build application and prune devDependencies afterward
RUN npm run build && \
    npm prune --omit=dev

# Production stage
FROM node:20-alpine AS production
WORKDIR /app

# Set production environment
ENV NODE_ENV=production

# Create non-root user
RUN addgroup -g 1001 -S nodejs && \
    adduser -S nodejs -u 1001

# Copy runtime dependencies and built output
COPY --from=builder --chown=nodejs:nodejs /app/node_modules ./node_modules
COPY --from=builder --chown=nodejs:nodejs /app/dist ./dist
COPY --from=builder --chown=nodejs:nodejs /app/package*.json ./

# Switch to non-root user
USER nodejs

# Expose port
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD node -e "require('http').get('http://localhost:3000/health', (r) => {process.exit(r.statusCode === 200 ? 0 : 1)})" || exit 1

# Start application
CMD ["node", "dist/index.js"]

# No-build variant (apps that run source directly):
# 1) In builder stage, replace install/build lines with:
#    RUN npm ci --omit=dev && npm cache clean --force
# 2) In production stage, replace COPY/CMD with:
#    COPY --from=builder --chown=nodejs:nodejs /app ./
#    CMD ["node", "src/index.js"]
