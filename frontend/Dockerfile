FROM node:20-slim

WORKDIR /app

# Install dependencies first (Docker layer cache)
COPY package.json ./
RUN npm install --legacy-peer-deps

# Copy application source
COPY . .

EXPOSE 3000

# Start Create React App dev server
CMD ["npm", "start"]
