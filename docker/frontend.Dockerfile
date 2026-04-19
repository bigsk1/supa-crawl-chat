FROM node:22-alpine

WORKDIR /app

# Install curl for testing
RUN apk add --no-cache curl

# Copy package.json and package-lock.json
COPY frontend/package*.json ./

# Install dependencies
RUN npm ci

# Copy the rest of the frontend code
COPY frontend/ ./

# Expose port 3000 for the dev server
EXPOSE 3001

# Start the development server
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3001"]