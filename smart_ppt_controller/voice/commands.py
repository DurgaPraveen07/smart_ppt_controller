import time
import speech_recognition as sr

AUDIO_OK = False
try:
    import sounddevice          # noqa — check availability
    import scipy.io.wavfile     # noqa
    AUDIO_OK = True
    print('[AUDIO] sounddevice backend available.')
except ImportError:
    pass

if not AUDIO_OK:
    try:
        import pyaudio          # noqa
        AUDIO_OK = True
        print('[AUDIO] PyAudio backend available.')
    except ImportError:
        print('[AUDIO] No audio backend found. Voice commands disabled.')


def listen_loop(apply_gesture_func, is_speech_active_func):
    """
    Voice recognition thread using sounddevice.
    Records 3-second audio chunks and sends to Google Speech API.
    """
    if not AUDIO_OK:
        print('[SPEECH] No audio backend -- voice commands disabled.')
        return

    try:
        import sounddevice as sd
        import wave
        import io
    except ImportError as ex:
        print(f'[SPEECH] sounddevice not available: {ex}')
        return

    recognizer  = sr.Recognizer()
    SAMPLE_RATE = 16000
    CHANNELS    = 1
    DURATION    = 3        # seconds to record per chunk

    print('[SPEECH] Voice recognition ready. Toggle mic in the UI.')

    while True:
        if not is_speech_active_func():
            time.sleep(0.3)
            continue
        try:
            recording = sd.rec(
                int(DURATION * SAMPLE_RATE),
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype='int16',
            )
            sd.wait()

            buf = io.BytesIO()
            with wave.open(buf, 'wb') as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(2)
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(recording.tobytes())
            buf.seek(0)

            audio_data = sr.AudioData(buf.read(), SAMPLE_RATE, 2)
            text = recognizer.recognize_google(audio_data).lower()
            print(f'[SPEECH] Heard: "{text}"')

            if any(w in text for w in ('next', 'forward', 'right')):
                apply_gesture_func('swipe_right')
            elif any(w in text for w in ('back', 'previous', 'left')):
                apply_gesture_func('swipe_left')
            elif any(w in text for w in ('start', 'first', 'beginning')):
                apply_gesture_func('thumbs_up')
            elif any(w in text for w in ('end', 'last')):
                apply_gesture_func('open_palm')

        except sr.UnknownValueError:
            pass
        except sr.RequestError as ex:
            print(f'[SPEECH] Google API error: {ex}')
        except Exception as ex:
            print(f'[SPEECH] Unexpected error: {ex}')
            time.sleep(1)
