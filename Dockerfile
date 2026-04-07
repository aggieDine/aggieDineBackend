FROM --platform=linux/amd64 public.ecr.aws/lambda/python:3.12

# Install system dependencies for Playwright/Chromium
RUN dnf update -y && \
    dnf install -y \
    atk cups-libs gtk3 libXcomposite libXcursor libXdamage \
    libXext libXi libXrandr libXScrnSaver libXtst pango \
    alsa-lib libdrm mesa-libgbm nss libX11 libxcb \
    libXinerama libX11-xcb libXfixes && \
    dnf clean all

# Install Python packages
RUN pip install --upgrade pip && \
    pip install playwright beautifulsoup4 boto3

# Install Playwright's bundled Chromium into a fixed path
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN playwright install chromium

# Copy all code
COPY . ${LAMBDA_TASK_ROOT}
RUN chmod -R 755 ${LAMBDA_TASK_ROOT}

CMD ["scrapers.hours_scraper.handler"]
