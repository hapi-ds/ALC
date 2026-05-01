# AlcoaBase CSV Runner - Playwright-based validation test runner
# Uses official Playwright image with pre-installed browsers.

FROM mcr.microsoft.com/playwright:v1.48.0-noble

WORKDIR /app

# Copy dependency files first for layer caching
COPY package.json package-lock.json ./

# Install Node.js dependencies
RUN npm ci

# Copy test files and utilities
COPY playwright.config.ts ./
COPY tests/ ./tests/
COPY utils/ ./utils/

# Create results directory
RUN mkdir -p /app/results

CMD ["npx", "playwright", "test"]
