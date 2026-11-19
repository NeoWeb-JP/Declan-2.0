"""Server startup and legacy response adapters with live dependencies."""


def main(*, r):
    return r.server_lifecycle.main(
        description=r.__doc__, argv=None, environ=r.os.environ,
        history_store=r.history, timer_store=r.timers,
        server_factory=r.ThreadingHTTPServer, handler=r.Handler,
        thread_factory=r.Thread, clock=r.monotonic,
        opener_factory=r.build_opener, proxy_factory=r.ProxyHandler,
        logger=r.DECLAN_EVENT_LOG, updates_module=r.updates, music_module=r.music,
        ha_connect=r.ha_device_connection, music_inventory=r.read_music_inventory_result,
        ip_address=r.ipaddress.ip_address, assist_port=r.ASSIST_PORT,
    )


def set_lights(name, desired_state, *, brightness=None, preview=False, require_all=False,
               relative_step=10, action_results=None, origin_device=None, r):
    return r.set_lights_result(
        name, desired_state, brightness=brightness, preview=preview,
        require_all=require_all, relative_step=relative_step,
        action_results=action_results, origin_device=origin_device,
    ).as_legacy_pair()


def end_headers(handler, *, r):
    r.http_ingress_security.send_security_headers(handler)
    return r.BaseHTTPRequestHandler.end_headers(handler)


def run(*, r):
    r.declan_logs.install()
    return r.main()
