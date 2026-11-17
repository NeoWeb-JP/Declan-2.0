FROM python:3.15-alpine@sha256:0f9552bb28711333da16915ec146f5e6bb44a7fdac9ced15dc17c2e0206346dd
WORKDIR /app
COPY proxy.py http_server.py security.py .
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import http.client; c=http.client.HTTPConnection('127.0.0.1', 8099, timeout=3); c.request('GET', '/'); r=c.getresponse(); c.close(); raise SystemExit(0 if r.status == 403 else 1)"
CMD ["python", "proxy.py"]
