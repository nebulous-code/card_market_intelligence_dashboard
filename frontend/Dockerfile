# Dockerfile for the Vue.js frontend service.
#
# Uses a two-stage build to separate dependency installation from the
# application code. This improves layer caching: if only source files
# change (not package.json), Docker reuses the cached node_modules layer
# and skips the npm install step entirely.
#
# Note: This Dockerfile runs the Vite development server, which is fine
# for local development and demo purposes. For a production deployment,
# this would be replaced with a build stage (npm run build) followed by
# an nginx stage to serve the compiled static files.

# Stage 1: Install dependencies.
# Named "deps" so it can be referenced by the next stage.
FROM node:20-slim AS deps
WORKDIR /app

# Copy only the package files and install dependencies.
# package-lock.json* with the wildcard means the COPY succeeds even
# if package-lock.json does not exist yet.
COPY package.json package-lock.json* ./
RUN npm install

# Stage 2: Development server.
# Starts fresh from the same base image and copies node_modules from Stage 1.
# This avoids any build artifacts or intermediate files from the install step.
FROM node:20-slim AS dev
WORKDIR /app

# Copy the installed node_modules from the deps stage.
COPY --from=deps /app/node_modules ./node_modules

# Copy the application source code.
COPY . .

# Document that the Vite dev server listens on port 5173.
EXPOSE 5173

# Start the Vite development server.
CMD ["npm", "run", "dev"]
