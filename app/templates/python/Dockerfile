FROM python:3.10-alpine

# 0. copy CA FIRST (before apk!)
COPY sophos_ca.crt /usr/local/share/ca-certificates/sophos_ca.crt

# 1. install ca-certificates WITHOUT HTTPS issues
RUN apk --no-cache add ca-certificates || true

# 2. trust your CA BEFORE updating repos
RUN update-ca-certificates

# 3. now APK works
RUN apk add --no-cache openssl

# 4. make Python trust same CA
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

COPY requirements.txt /tmp/
RUN pip install --upgrade pip && \
    pip install -r /tmp/requirements.txt
COPY ./src /src
CMD python /src/app.py
