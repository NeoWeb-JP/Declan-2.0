"""HTTP adapters for browser speech-to-text and text-to-speech."""

def transcribe_browser_audio(handler, *, web_stt, connection_factory, transcribe, token, pipeline, logger):
    if handler.headers.get_content_type() != "application/octet-stream":
        handler.send_json(415, {"error": "Expected microphone audio."})
        return
    try:
        size = int(handler.headers.get("Content-Length", "0"))
        if not 0 < size <= web_stt.MAX_AUDIO_BYTES or size % 2:
            raise ValueError
    except ValueError:
        handler.send_json(400, {"error": "Record up to 20 seconds of microphone audio."})
        return
    connection = connection_factory()
    if connection is None:
        handler.send_json(503, {"error": "Home Assistant isn't configured."})
        return
    audio = handler.rfile.read(size)
    if len(audio) != size:
        handler.send_json(400, {"error": "The microphone recording was incomplete."})
        return
    try:
        result = transcribe(connection[0], token, audio,
                                  pipeline=pipeline)
    except ImportError:
        handler.send_json(503, {"error": "Install requirements-web-voice.txt to enable the Assist microphone."})
        return
    except web_stt.AssistSpeechError as error:
        logger.warning("web_assist_transcription_failed code=%s", error.code)
        handler.send_json(502, {"error": f"Home Assistant speech recognition failed ({error.code})."})
        return
    except (OSError, ValueError, AttributeError, TypeError) as error:
        logger.warning("web_assist_connection_failed exception_type=%s", type(error).__name__)
        handler.send_json(502, {"error": "Home Assistant couldn't transcribe that recording."})
        return
    handler.send_json(200, {"text": result.text})

def render_tts(handler, message, *, render):
    audio = render(message)
    if audio is None:
        handler.send_json(503, {"error": "Declan's voice is unavailable."})
    else:
        handler.send_body(200, audio, "audio/mpeg")
