# Build stage
FROM node:16-alpine as build-stage

# Set working directory
WORKDIR /app

# Add build arguments
ARG NODE_ENV=production
ARG API_URL

# Set environment variables
ENV NODE_ENV=$NODE_ENV
ENV VUE_APP_API_URL=$API_URL

# Configure npm to use taobao registry
RUN npm config set registry https://registry.npmmirror.com

# Copy package files
COPY package*.json ./

# Install dependencies (including dev dependencies for build)
RUN npm install --prefer-offline --no-audit --production=false

# Copy project files
COPY . .

# Build app
RUN npm run build

# Production stage
FROM nginx:stable-alpine as production-stage

# Add runtime configurations
RUN mkdir -p /usr/share/nginx/html/config

# Copy built files from build stage
COPY --from=build-stage /app/dist /usr/share/nginx/html

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Add health check
HEALTHCHECK --interval=30s --timeout=3s \
    CMD wget --quiet --tries=1 --spider http://localhost:80/ || exit 1

# Expose port 80
EXPOSE 80

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
