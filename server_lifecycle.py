"""HTTP server startup, health verification and periodic maintenance lifecycle."""
import argparse
import json
import logging
from threading import Lock, Thread
from urllib.error import URLError


def single_flight_runner(thread_factory=Thread):
    """Return run(name, job) that runs a job on a daemon thread, one at a time per name.

    A job that is still running when it comes due again is skipped, so a slow
    Home Assistant can neither stack up threads nor stall the supervisor loop.
    """
    lock = Lock()
    active = set()

    def run(name, job):
        with lock:
            if name in active:
                return False
            active.add(name)

        def work():
            try:
                job()
            finally:
                with lock:
                    active.discard(name)

        thread_factory(target=work, daemon=True, name=f"declan-{name}").start()
        return True

    return run


def _inline(name, job):
    job()
    return True


def main(*, description, argv, environ, history_store, timer_store, server_factory, handler, thread_factory, clock, opener_factory, proxy_factory, logger, updates_module, music_module, ha_connect, music_inventory, ip_address, assist_port, run_background=None):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--assist-lan", action="store_true", help="Allow the authenticated Assist endpoint on the LAN.")
    parser.add_argument("--port", type=int, help="Override the default port (8765, or 52737 in Assist LAN mode).")
    args = parser.parse_args(argv)
    port = args.port if args.port is not None else (assist_port if args.assist_lan else 8765)
    if not 0 <= port <= 65535:
        parser.error("--port must be between 0 and 65535.")
    if args.assist_lan and port == 0:
        parser.error("Assist LAN mode needs a fixed port. Omit --port to use 52737.")
    if args.assist_lan and len(environ.get("DECLAN_ASSIST_TOKEN", "")) < 32:
        parser.error("--assist-lan requires a DECLAN_ASSIST_TOKEN of at least 32 characters.")
    history_store.retention_seconds()  # Reject invalid retention before accepting requests.
    repair = getattr(history_store, "repair_data_location", None)
    if callable(repair):
        repair(logger)  # Recover data 2.13.0/2.13.1-rc1 wrote inside the release folder.
    history_store.initialize()
    timer_store.initialize()
    # Assist LAN mode explicitly exposes the server to configured LAN clients;
    # the Assist token is validated above before opening the listener.
    bind_address = "0.0.0.0" if args.assist_lan else "127.0.0.1"  # nosec B104
    if args.assist_lan:
        bind_address = environ.get('DECLAN_BIND_ADDRESS', bind_address)
        try:
            address = ip_address(bind_address)
            if address.version != 4:
                raise ValueError
        except ValueError:
            parser.error('DECLAN_BIND_ADDRESS must be an IPv4 address.')
    try:
        server = server_factory((bind_address, port), handler)
    except OSError as error:
        parser.exit(1, f"Declan could not open port {port}: {error}\n")
    with server:
        worker = thread_factory(target=server.serve_forever, daemon=True)
        worker.start()
        next_prune = clock()
        background = run_background or _inline
        next_music_check = clock() + 5
        url = f"http://127.0.0.1:{server.server_port}"
        try:
            opener = opener_factory(proxy_factory({}))
            with opener.open(url + "/health", timeout=3) as response:
                if json.load(response) != {"status": "ok"}:
                    raise ValueError("Unexpected health response.")
            logger.info("Declan backend started and health check passed (port %d)", server.server_port)
            while worker.is_alive():
                worker.join(timeout=0.5)
                if updates_module.RUNTIME.restart.is_set():
                    logger.info("Restarting Declan to activate selected release")
                    raise SystemExit(75)
                try:
                    timer_store.ring_due(opener)
                except Exception:
                    logging.exception("Timer alarms could not be checked.")
                if clock() >= next_music_check:
                    next_music_check = clock() + 5
                    def check_music():
                        try:
                            music_module.skip_blocked_tracks(ha_connect(), music_inventory)
                        except Exception:
                            logging.exception("Blocked music could not be checked.")
                    background("blocked-music", check_music)
                    def check_entrances():
                        try:
                            from declan.ha import entrance_themes
                            entrance_themes.due_with_opener(opener)
                        except Exception:
                            logging.exception("Entrance themes could not be checked.")
                    background("entrance-themes", check_entrances)
                if clock() >= next_prune:
                    def prune_history():
                        try:
                            history_store.prune()
                        except Exception:
                            logging.exception("Conversation history could not be pruned.")
                    background("history-prune", prune_history)
                    next_prune = clock() + 3600
        except (URLError, TimeoutError, ValueError) as error:
            parser.exit(1, f"Declan bound {url} but its local health check failed: {error}\n")
        except KeyboardInterrupt:
            logger.info("Declan backend stopped by keyboard interrupt")
        finally:
            server.shutdown()
            worker.join()
