import os
import cv2
import time
import threading
from flask import Flask, render_template, Response, jsonify, request, send_file
from werkzeug.utils import secure_filename

from smart_ppt_controller.ppt.controller import (
    state, state_lock, UPLOAD_DIR, SLIDES_DIR, ALLOWED_EXT,
    clear_slides, convert_pdf, convert_pptx, slide_images, apply_gesture,
    FITZ_OK, WIN32_OK
)
from smart_ppt_controller.gesture.recognizer import (
    detect_gesture, reset_gesture_state, MP_OK
)
from smart_ppt_controller.voice.commands import (
    listen_loop, AUDIO_OK
)

# Package resource resolution for web templates and static assets
def _get_web_dirs():
    try:
        from importlib.resources import files
        web_pkg = files("smart_ppt_controller.web")
        t_dir = str(web_pkg.joinpath("templates"))
        s_dir = str(web_pkg.joinpath("static"))
        if os.path.exists(t_dir):
            return t_dir, s_dir
    except Exception:
        pass
    mod_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(mod_dir, "web", "templates"), os.path.join(mod_dir, "web", "static")

template_dir, static_dir = _get_web_dirs()
app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)

# Camera / speech state
camera_active = False
speech_active = False
cap           = None
cap_lock      = threading.Lock()


def is_speech_active():
    return speech_active


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


@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/toggle_camera', methods=['POST'])
def toggle_camera():
    global cap, camera_active
    with cap_lock:
        if not camera_active:
            c = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            if not c.isOpened():
                return jsonify(status='error', message='Cannot open camera'), 500
            c.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
            c.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            c.set(cv2.CAP_PROP_FPS, 30)
            cap = c
            camera_active = True
            reset_gesture_state()
            return jsonify(status='Camera Started')
        else:
            camera_active = False
            if cap:
                cap.release()
                cap = None
            return jsonify(status='Camera Stopped')


@app.route('/toggle_mic', methods=['POST'])
def toggle_mic():
    global speech_active
    speech_active = not speech_active
    return jsonify(status='Mic Active' if speech_active else 'Mic Muted')


def start_app(host="0.0.0.0", port=5000, debug=False):
    """Launch Smart PPT Controller server."""
    threading.Thread(target=listen_loop, args=(apply_gesture, is_speech_active), daemon=True).start()
    print('\n' + '='*55)
    print('  Smart PPT Controller')
    print(f'  CV backend  : {"MediaPipe Hands [OK]" if MP_OK else "Skin-colour (fallback)"}')
    print(f'  Audio       : {"Available [OK]" if AUDIO_OK else "Unavailable -- voice commands off"}')
    print(f'  Browser     :  http://localhost:{port}')
    print('='*55 + '\n')
    app.run(debug=debug, host=host, port=port, threaded=True)


if __name__ == '__main__':
    start_app()
