FROM mcr.microsoft.com/playwright/python:v1.58.0-noble@sha256:678457c4c323b981d8b4befc57b95366bb1bb6aa30057b1269f6b171e8d9975a
RUN pip install --no-cache-dir playwright==1.58.0 greenlet==3.5.6 pyee==13.0.1 typing-extensions==4.16.0
RUN python -c "import urllib.request; urllib.request.urlretrieve('https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.11.0/axe.min.js','/opt/axe.min.js')"
RUN echo 'e9e5863c33a874f09bc01acd9234b7e3c871479f5eef8802fa582544465e6d01  /opt/axe.min.js' | sha256sum -c -
WORKDIR /app
