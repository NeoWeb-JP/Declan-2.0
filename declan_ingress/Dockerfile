FROM python:3.12-alpine
WORKDIR /app
COPY proxy.py http_server.py security.py .
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import http.client; c=http.client.HTTPConnection('127.0.0.1', 8099, timeout=3); c.request('GET', '/'); r=c.getresponse(); c.close(); raise SystemExit(0 if r.status == 403 else 1)"
CMD ["python", "proxy.py"]
