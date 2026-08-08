import cv2
import os
import time
import threading
import numpy as np

import speech_recognition as sr
from flask import Flask, render_template, Response, jsonify, request, send_file
from werkzeug.utils import secure_filename

# ── Optional deps ─────────────────────────────────────────────────
try:
    import fitz  # pymupdf — PDF rendering
    FITZ_OK = True
except ImportError:
    FITZ_OK = False

try:
    import win32com.client
    import pythoncom
    WIN32_OK = True
except ImportError:
    WIN32_OK = False

# ── MediaPipe Tasks API (v0.10+) — GestureRecognizer VIDEO mode ──────────
_mp_gesture    = None
MP_OK = False

_MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'gesture_recognizer.task')

try:
    from mediapipe.tasks.python import vision as _mpv
    from mediapipe.tasks.python.core import base_options as _mpbo

    if os.path.exists(_MODEL_PATH):
        _gr_opts = _mpv.GestureRecognizerOptions(
            base_options=_mpbo.BaseOptions(model_asset_path=_MODEL_PATH),
            running_mode=_mpv.RunningMode.VIDEO,   # VIDEO = smooth real-time tracking
            num_hands=1,
            min_hand_detection_confidence=0.6,
            min_hand_presence_confidence=0.6,
            min_tracking_confidence=0.5,
        )
        _mp_gesture = _mpv.GestureRecognizer.create_from_options(_gr_opts)
        MP_OK = True
        print('[CV] MediaPipe GestureRecognizer (VIDEO mode) loaded -- accurate tracking active.')
    else:
        print('[CV] gesture_recognizer.task not found -- using skin-colour fallback.')
except Exception as _e:
    MP_OK = False
    print(f'[CV] MediaPipe Tasks unavailable ({_e}) -- using skin-colour fallback.')

# ── Audio backend (sounddevice beats PyAudio on Python 3.13+) ─────
AUDIO_OK = False
try:
    import sounddevice          # noqa — just checking availability
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

# ── Flask app ─────────────────────────────────────────────────────
app = Flask(__name__)
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR  = os.path.join(BASE_DIR, 'uploads')
SLIDES_DIR  = os.path.join(BASE_DIR, 'static', 'slides')
ALLOWED_EXT = {'.ppt', '.pptx', '.pdf'}

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(SLIDES_DIR, exist_ok=True)

# ── Presentation state ────────────────────────────────────────────
state = {
    'current': 0,
    'total':   0,
    'loaded':  False,
    'title':   '',
}
state_lock = threading.Lock()

# ── Camera / speech state ─────────────────────────────────────────
camera_active = False
speech_active = False
cap           = None
cap_lock      = threading.Lock()

# Gesture tracking
_prev_wrist_x  = 0          # wrist x for swipe detection
_last_action   = 0.0
COOLDOWN       = 0.8        # sec between gesture actions
SWIPE_THRESH   = 0.12       # normalised wrist delta (0..1) for swipe


# ═══════════════════════════════════════════════════════════════════
# SLIDE CONVERSION
# ═══════════════════════════════════════════════════════════════════

def clear_slides():
    """Remove all previously converted slide images."""
    for f in os.listdir(SLIDES_DIR):
        os.remove(os.path.join(SLIDES_DIR, f))


def convert_pdf(path):
    """Render PDF pages to JPEG images. Returns slide count."""
    if not FITZ_OK:
        return 0
    doc = fitz.open(path)
    mat = fitz.Matrix(1.8, 1.8)
    for i, page in enumerate(doc):
        pix = page.get_pixmap(matrix=mat)
        pix.save(os.path.join(SLIDES_DIR, f'slide_{i:04d}.jpg'))
    return len(doc)


def convert_pptx(path):
    """Use PowerPoint COM (Windows) to export each slide as JPEG. Returns count."""
    if not WIN32_OK:
        return 0
    pythoncom.CoInitialize()
    total = 0
    try:
        pp   = win32com.client.Dispatch("PowerPoint.Application")
        pp.Visible = 1
        pres = pp.Presentations.Open(os.path.abspath(path), WithWindow=False)
        total = pres.Slides.Count
        for i in range(1, total + 1):
            out = os.path.abspath(os.path.join(SLIDES_DIR, f'slide_{i-1:04d}.jpg'))
            pres.Slides(i).Export(out, "JPG", 1280, 720)
        pres.Close()
        pp.Quit()
    except Exception as e:
        print(f'[PPTX] COM error: {e}')
        total = 0
    finally:
        pythoncom.CoUninitialize()
    return total


def slide_images():
    """Return sorted list of slide image filenames."""
    return sorted(
        f for f in os.listdir(SLIDES_DIR) if f.endswith('.jpg')
    )



def _draw_hand_landmarks_pro(frame, hand_landmarks):
    """
    Draw hand skeleton exactly like the reference image:
    - Red lines for all bone connections
    - Green filled dots at every joint (with red border)
    """
    H, W = frame.shape[:2]
    lm = hand_landmarks

    # All 21-landmark connections (matching MediaPipe HandLandmarker topology)
    CONNECTIONS = [
        # Thumb
        (0, 1), (1, 2), (2, 3), (3, 4),
        # Index finger
        (0, 5), (5, 6), (6, 7), (7, 8),
        # Middle finger
        (0, 9), (9, 10), (10, 11), (11, 12),
        # Ring finger
        (0, 13), (13, 14), (14, 15), (15, 16),
        # Pinky
        (0, 17), (17, 18), (18, 19), (19, 20),
        # Palm cross-connections
        (5, 9), (9, 13), (13, 17), (0, 5), (0, 17),
    ]

    # Draw red connection lines first (behind the dots)
    for s, e in CONNECTIONS:
        x1 = int(lm[s].x * W); y1 = int(lm[s].y * H)
        x2 = int(lm[e].x * W); y2 = int(lm[e].y * H)
        cv2.line(frame, (x1, y1), (x2, y2), (0, 0, 220), 2)

    # Draw green dots with red border at each landmark
    TIP_IDS = {4, 8, 12, 16, 20}   # fingertips get slightly larger dot
    for i in range(21):
        x = int(lm[i].x * W); y = int(lm[i].y * H)
        r = 7 if i in TIP_IDS else 5
        cv2.circle(frame, (x, y), r,     (0, 0, 200),   -1)  # red fill
        cv2.circle(frame, (x, y), r - 2, (0, 220, 0),   -1)  # green inner



def detect_gesture_mp(frame):
    """
    MediaPipe GestureRecognizer in VIDEO mode (real-time, smooth tracking).
    Returns (gesture | None, annotated_frame).
    """
    global _prev_wrist_x, _last_action

    try:
        import mediapipe as mp
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image  = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        ts_ms     = int(time.time() * 1000)   # monotonic ms timestamp for VIDEO mode
        result    = _mp_gesture.recognize_for_video(mp_image, ts_ms)
    except Exception as ex:
        return None, frame

    if not result.hand_landmarks or not result.gestures:
        _prev_wrist_x = 0
        return None, frame

    # Draw professional skeleton — green dots + red lines (like reference image)
    _draw_hand_landmarks_pro(frame, result.hand_landmarks[0])

    lm      = result.hand_landmarks[0]
    wrist_x = lm[0].x     # normalised 0..1
    now     = time.time()
    gesture = None

    # ── Swipe detection — wrist horizontal movement ──────────────
    if _prev_wrist_x != 0 and (now - _last_action) > COOLDOWN:
        delta = wrist_x - _prev_wrist_x
        if delta > SWIPE_THRESH:
            gesture      = 'swipe_right'
            _last_action = now
        elif delta < -SWIPE_THRESH:
            gesture      = 'swipe_left'
            _last_action = now

    # ── Static gesture from GestureRecognizer ────────────────────
    if gesture is None and (now - _last_action) > COOLDOWN:
        raw = result.gestures[0][0].category_name   # e.g. "Thumb_Up"
        mp_to_our = {
            'Thumb_Up':    'thumbs_up',
            'Open_Palm':   'open_palm',
            'Pointing_Up': 'index_only',
            'Victory':     'victory',
            'Closed_Fist': 'fist',
            'ILoveYou':    'open_palm',
        }
        if raw in mp_to_our:
            gesture      = mp_to_our[raw]
            _last_action = now

    _prev_wrist_x = wrist_x

    label_map = {
        'open_palm':  'Open Palm',
        'index_only': 'Index Finger',
        'victory':    'Victory Finger',
        'thumbs_up':  'Thumbs Up',
        'swipe_right':'Swipe Right ->',
        'swipe_left': '<- Swipe Left',
        'fist':       'Fist',
    }
    raw_name = result.gestures[0][0].category_name if result.gestures else ''
    label    = label_map.get(gesture, raw_name)
    if label:
        # Black pill background for readability on any background
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        cv2.rectangle(frame, (10, 8), (20 + tw, 20 + th + 12), (0, 0, 0), cv2.FILLED)
        cv2.putText(frame, label, (14, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 230, 0), 2, cv2.LINE_AA)
    return gesture, frame



# ── Fallback: skin-colour detection (used only if MediaPipe fails) ─

def detect_gesture_skin(frame):
    """Legacy skin-colour + convex-hull finger counter."""
    global _prev_wrist_x, _last_action

    ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
    lo    = np.array([0,   133, 77],  dtype=np.uint8)
    hi    = np.array([255, 173, 127], dtype=np.uint8)
    mask  = cv2.inRange(ycrcb, lo, hi)

    k    = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  k)

    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None, frame

    hand = max(cnts, key=cv2.contourArea)
    if cv2.contourArea(hand) < 6000:
        return None, frame

    cv2.drawContours(frame, [hand], -1, (99, 102, 241), 2)
    x, y, w, h = cv2.boundingRect(hand)
    cx_norm = (x + w // 2) / frame.shape[1]

    now = time.time()
    gesture = None

    hull    = cv2.convexHull(hand, returnPoints=False)
    defects = cv2.convexityDefects(hand, hull)
    fingers = 0
    if defects is not None:
        for i in range(defects.shape[0]):
            s, e, f, d = defects[i, 0]
            start = tuple(hand[s][0]); end = tuple(hand[e][0]); far = tuple(hand[f][0])
            a = np.linalg.norm(np.array(end) - np.array(start))
            b = np.linalg.norm(np.array(far) - np.array(start))
            c = np.linalg.norm(np.array(end) - np.array(far))
            cos_a = (b**2 + c**2 - a**2) / (2 * b * c + 1e-6)
            if np.degrees(np.arccos(np.clip(cos_a, -1, 1))) < 80:
                fingers += 1

    if (now - _last_action) > COOLDOWN:
        if fingers >= 4:
            gesture = 'open_palm'; _last_action = now
        elif fingers == 1:
            gesture = 'victory'; _last_action = now
        elif fingers == 0:
            if h > w * 1.5:
                gesture = 'index_only'
            else:
                gesture = 'thumbs_up' if h > w * 1.2 else 'fist'
            _last_action = now

    if _prev_wrist_x != 0 and (now - _last_action) > COOLDOWN:
        delta = cx_norm - _prev_wrist_x
        if delta > SWIPE_THRESH:
            gesture = 'swipe_right'; _last_action = now
        elif delta < -SWIPE_THRESH:
            gesture = 'swipe_left'; _last_action = now

    _prev_wrist_x = cx_norm
    label_map = {
        'open_palm':  '✋ Open Palm',
        'index_only': '☝️ Index Finger',
        'victory':    '✌️ Victory Finger',
        'thumbs_up':  '👍 Thumbs Up',
        'swipe_right':'☝️ Swipe Right',
        'swipe_left': '✌️ Swipe Left',
        'fist':       '✊ Fist',
    }
    label = label_map.get(gesture, '')
    if label:
        cv2.putText(frame, label, (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (167, 139, 250), 2, cv2.LINE_AA)
    return gesture, frame


def detect_gesture(frame):
    """Route to best available gesture detector."""
    if MP_OK:
        gesture, frame = detect_gesture_mp(frame)
        return gesture, frame, 0
    else:
        gesture, frame = detect_gesture_skin(frame)
        return gesture, frame, 0


def apply_gesture(gesture):
    """Map a detected gesture to a slide action."""
    if not state['loaded']:
        return
    with state_lock:
        if gesture == 'swipe_right':
            state['current'] = min(state['current'] + 1, state['total'] - 1)
        elif gesture == 'swipe_left':
            state['current'] = max(state['current'] - 1, 0)
        elif gesture == 'thumbs_up':
            state['current'] = 0
        elif gesture == 'open_palm':
            state['current'] = state['total'] - 1
        elif gesture == 'index_only':
            state['current'] = min(state['current'] + 1, state['total'] - 1)
        elif gesture == 'victory':
            state['current'] = max(state['current'] - 1, 0)


def generate_frames():
    """MJPEG generator for the /video_feed route."""
    global cap, camera_active
    while camera_active:
        with cap_lock:
            if cap is None or not cap.isOpened():
                break
            ok, frame = cap.read()
        if not ok:
            break
        frame = cv2.flip(frame, 1)
        gesture, frame, _ = detect_gesture(frame)
        if gesture:
            apply_gesture(gesture)
        _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' +
               buf.tobytes() + b'\r\n')


# ═══════════════════════════════════════════════════════════════════
# FLASK ROUTES
# ═══════════════════════════════════════════════════════════════════

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/status')
def status():
    return jsonify(server='ok', fitz=FITZ_OK, win32=WIN32_OK,
                   mediapipe=MP_OK, audio=AUDIO_OK,
                   camera=camera_active, mic=speech_active,
                   presentation=state['loaded'])


# ── Presentation upload ──────────────────────────────────────────

@app.route('/upload_presentation', methods=['POST'])
def upload_presentation():
    if 'file' not in request.files:
        return jsonify(error='No file'), 400
    f = request.files['file']
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        return jsonify(error=f'Unsupported type {ext}'), 400

    filename = secure_filename(f.filename)
    path     = os.path.join(UPLOAD_DIR, filename)
    f.save(path)

    clear_slides()
    with state_lock:
        state['loaded']  = False
        state['current'] = 0
        state['total']   = 0
        state['title']   = filename

    if ext == '.pdf':
        total = convert_pdf(path)
    else:
        total = convert_pptx(path)

    if total == 0:
        return jsonify(error='Could not convert file. Ensure PowerPoint is installed for .pptx, or pymupdf for .pdf.'), 500

    with state_lock:
        state['total']  = total
        state['loaded'] = True

    return jsonify(status='ok', total=total, title=filename)


# ── Slide navigation ─────────────────────────────────────────────

@app.route('/slide/state')
def slide_state():
    with state_lock:
        return jsonify(**state)


@app.route('/slide/next', methods=['POST'])
def slide_next():
    with state_lock:
        if state['loaded']:
            state['current'] = min(state['current'] + 1, state['total'] - 1)
        return jsonify(**state)


@app.route('/slide/prev', methods=['POST'])
def slide_prev():
    with state_lock:
        if state['loaded']:
            state['current'] = max(state['current'] - 1, 0)
        return jsonify(**state)


@app.route('/slide/goto/<int:n>', methods=['POST'])
def slide_goto(n):
    with state_lock:
        if state['loaded']:
            state['current'] = max(0, min(n, state['total'] - 1))
        return jsonify(**state)


@app.route('/slide/image/<int:n>')
def slide_image(n):
    imgs = slide_images()
    if not imgs or n >= len(imgs):
        return '', 404
    return send_file(os.path.join(SLIDES_DIR, imgs[n]), mimetype='image/jpeg')


# ── Camera ───────────────────────────────────────────────────────

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/toggle_camera', methods=['POST'])
def toggle_camera():
    global cap, camera_active, _prev_wrist_x
    with cap_lock:
        if not camera_active:
            c = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            if not c.isOpened():
                return jsonify(status='error', message='Cannot open camera'), 500
            c.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
            c.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            c.set(cv2.CAP_PROP_FPS, 30)
            cap = c
            camera_active  = True
            _prev_wrist_x  = 0
            return jsonify(status='Camera Started')
        else:
            camera_active = False
            if cap:
                cap.release()
                cap = None
            return jsonify(status='Camera Stopped')


# ── Microphone ───────────────────────────────────────────────────

@app.route('/toggle_mic', methods=['POST'])
def toggle_mic():
    global speech_active
    speech_active = not speech_active
    return jsonify(status='Mic Active' if speech_active else 'Mic Muted')


# ═══════════════════════════════════════════════════════════════════
# SPEECH RECOGNITION THREAD
# ═══════════════════════════════════════════════════════════════════

def listen_loop():
    """
    Voice recognition thread using sounddevice (no PyAudio required).
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

    print('[SPEECH] Voice recognition ready (sounddevice). Toggle mic in the UI.')

    while True:
        if not speech_active:
            time.sleep(0.3)
            continue
        try:
            # Record a chunk of audio
            recording = sd.rec(
                int(DURATION * SAMPLE_RATE),
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype='int16',
            )
            sd.wait()           # block until recording is done

            # Wrap in an in-memory WAV for SpeechRecognition
            buf = io.BytesIO()
            with wave.open(buf, 'wb') as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(2)        # 16-bit = 2 bytes
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(recording.tobytes())
            buf.seek(0)

            audio_data = sr.AudioData(buf.read(), SAMPLE_RATE, 2)
            text = recognizer.recognize_google(audio_data).lower()
            print(f'[SPEECH] Heard: "{text}"')

            if any(w in text for w in ('next', 'forward', 'right')):
                apply_gesture('swipe_right')
            elif any(w in text for w in ('back', 'previous', 'left')):
                apply_gesture('swipe_left')
            elif any(w in text for w in ('start', 'first', 'beginning')):
                apply_gesture('thumbs_up')
            elif any(w in text for w in ('end', 'last')):
                apply_gesture('open_palm')

        except sr.UnknownValueError:
            pass   # silence or unrecognised speech
        except sr.RequestError as ex:
            print(f'[SPEECH] Google API error: {ex}')
        except Exception as ex:
            print(f'[SPEECH] Unexpected error: {ex}')
            time.sleep(1)


# ═══════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    threading.Thread(target=listen_loop, daemon=True).start()
    print('\n' + '='*55)
    print('  Gesture PPT Controller')
    print(f'  CV backend  : {"MediaPipe Hands [OK]" if MP_OK else "Skin-colour (fallback)"}')
    print(f'  Audio       : {"Available [OK]" if AUDIO_OK else "Unavailable -- voice commands off"}')
    print('  Browser     :  http://localhost:5000')
    print('='*55 + '\n')
    app.run(debug=False, host='0.0.0.0', port=5000, threaded=True)
