# 1. Force Intel architecture for Chrome compatibility
FROM --platform=linux/amd64 public.ecr.aws/lambda/python:3.11

# Install Chrome dependencies (Added nss, libX11, and libxcb)
RUN yum update -y && \
    yum install -y wget unzip atk cups-libs gtk3 libXcomposite libXcursor \
    libXdamage libXext libXi libXrandr libXScrnSaver libXtst pango \
    alsa-lib libdrm mesa-libgbm xorg-x11-utils nss libX11 libxcb \
    libXinerama libXv xorg-x11-fonts-Type1 xorg-x11-fonts-75dpi

# 3. Install Chrome using 'yum' instead of 'microdnf'
RUN wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_x86_64.rpm && \
    yum install -y ./google-chrome-stable_current_x86_64.rpm && \
    rm google-chrome-stable_current_x86_64.rpm && \
    yum clean all

# Install ChromeDriver matching the exact Chrome version
RUN CHROME_MAJOR_VERSION=$(google-chrome --version | sed -E 's/.* ([0-9]+)(\.[0-9]+){3}.*/\1/') && \
    echo "Installing ChromeDriver for version ${CHROME_MAJOR_VERSION}" && \
    DRIVER_VER=$(wget -qO- "https://googlechromelabs.github.io/chrome-for-testing/LATEST_RELEASE_${CHROME_MAJOR_VERSION}") && \
    wget -q "https://storage.googleapis.com/chrome-for-testing-public/${DRIVER_VER}/linux64/chromedriver-linux64.zip" && \
    unzip chromedriver-linux64.zip && \
    mv chromedriver-linux64/chromedriver /usr/local/bin/ && \
    chmod +x /usr/local/bin/chromedriver && \
    rm -rf chromedriver-linux64.zip chromedriver-linux64

# 1. Swap selenium and stealth for seleniumbase
RUN pip install seleniumbase beautifulsoup4 boto3

RUN ln -s /tmp/uc_driver /var/lang/lib/python3.11/site-packages/seleniumbase/drivers/uc_driver

# 2. Tell SeleniumBase to do all its behind-the-scenes patching in /tmp
ENV HOME=/tmp

# Copy code and FIX PERMISSIONS
COPY . ${LAMBDA_TASK_ROOT}
RUN chmod -R 755 ${LAMBDA_TASK_ROOT}

CMD ["scrapers.hours_scraper.handler"]