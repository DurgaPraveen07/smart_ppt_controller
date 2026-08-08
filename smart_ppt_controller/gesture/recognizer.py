import os
import time
import numpy as np
import cv2

# Locate MediaPipe .task model reliably across installs
def _get_model_path():
    try:
        from importlib.resources import files
        model_path = str(files("smart_ppt_controller.models").joinpath("gesture_recognizer.task"))
        if os.path.exists(model_path):
            return model_path
    except Exception:
        pass
    mod_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(mod_dir), "models", "gesture_recognizer.task")

_MODEL_PATH = _get_model_path()
_mp_gesture = None
MP_OK = False

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
        print(f'[CV] gesture_recognizer.task not found at {_MODEL_PATH} -- using skin-colour fallback.')
except Exception as _e:
    MP_OK = False
    print(f'[CV] MediaPipe Tasks unavailable ({_e}) -- using skin-colour fallback.')

# Gesture tracking globals
_prev_wrist_x  = 0          # wrist x for swipe detection
_last_action   = 0.0
COOLDOWN       = 0.8        # sec between gesture actions
SWIPE_THRESH   = 0.12       # normalised wrist delta (0..1) for swipe


def reset_gesture_state():
    global _prev_wrist_x, _last_action
    _prev_wrist_x = 0
    _last_action = 0.0


def _draw_hand_landmarks_pro(frame, hand_landmarks):
    """
    Draw hand skeleton:
    - Red lines for all bone connections
    - Green filled dots at every joint (with red border)
    """
    H, W = frame.shape[:2]
    lm = hand_landmarks

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

    for s, e in CONNECTIONS:
        x1 = int(lm[s].x * W); y1 = int(lm[s].y * H)
        x2 = int(lm[e].x * W); y2 = int(lm[e].y * H)
        cv2.line(frame, (x1, y1), (x2, y2), (0, 0, 220), 2)

    TIP_IDS = {4, 8, 12, 16, 20}
    for i in range(21):
        x = int(lm[i].x * W); y = int(lm[i].y * H)
        r = 7 if i in TIP_IDS else 5
        cv2.circle(frame, (x, y), r,     (0, 0, 200),   -1)
        cv2.circle(frame, (x, y), r - 2, (0, 220, 0),   -1)


def detect_gesture_mp(frame):
    """MediaPipe GestureRecognizer in VIDEO mode."""
    global _prev_wrist_x, _last_action

    try:
        import mediapipe as mp
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image  = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        ts_ms     = int(time.time() * 1000)
        result    = _mp_gesture.recognize_for_video(mp_image, ts_ms)
    except Exception:
        return None, frame

    if not result.hand_landmarks or not result.gestures:
        _prev_wrist_x = 0
        return None, frame

    _draw_hand_landmarks_pro(frame, result.hand_landmarks[0])

    lm      = result.hand_landmarks[0]
    wrist_x = lm[0].x
    now     = time.time()
    gesture = None

    if _prev_wrist_x != 0 and (now - _last_action) > COOLDOWN:
        delta = wrist_x - _prev_wrist_x
        if delta > SWIPE_THRESH:
            gesture      = 'swipe_right'
            _last_action = now
        elif delta < -SWIPE_THRESH:
            gesture      = 'swipe_left'
            _last_action = now

    if gesture is None and (now - _last_action) > COOLDOWN:
        raw = result.gestures[0][0].category_name
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
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        cv2.rectangle(frame, (10, 8), (20 + tw, 20 + th + 12), (0, 0, 0), cv2.FILLED)
        cv2.putText(frame, label, (14, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 230, 0), 2, cv2.LINE_AA)
    return gesture, frame


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
        'open_palm':  'Open Palm',
        'index_only': 'Index Finger',
        'victory':    'Victory Finger',
        'thumbs_up':  'Thumbs Up',
        'swipe_right':'Swipe Right',
        'swipe_left': 'Swipe Left',
        'fist':       'Fist',
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
