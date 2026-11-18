"""System read endpoints, called only after server-level access checks."""

ROUTES = frozenset({"/", "/logo.png", "/health", "/health/dependencies", "/api/capabilities"})


def handles(path):
    return path in ROUTES


def dispatch(handler, *, logo_path, health_readiness, ha_status, release_version):
    path = handler.path
    if path == "/":
        handler.send_json(404, {"error": "Use the native Declan Home Assistant panel."})
    elif path == "/logo.png":
        handler.send_body(200, logo_path.read_bytes(), "image/png")
    elif path == "/health":
        status, payload = health_readiness.database_health_response()
        handler.send_json(status, payload)
    elif path == "/health/dependencies":
        health = health_readiness.DependencyHealth(
            database=health_readiness.database_ready(),
            home_assistant=ha_status(),
        )
        status, payload = health.response()
        handler.send_json(status, payload)
    elif path == "/api/capabilities":
        handler.send_json(200, {
            "api_version": "1.0",
            "server_version": release_version,
            "capabilities": ["updates", "ha_status"],
        })
    else:
        raise ValueError("Unsupported system read route")
