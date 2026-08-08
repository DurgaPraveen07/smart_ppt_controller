import os
import threading

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


# Determine runtime directories safely (user home directory fallback)
def _get_runtime_dir():
    try:
        user_dir = os.path.join(os.path.expanduser("~"), ".smart_ppt_controller")
        os.makedirs(user_dir, exist_ok=True)
        return user_dir
    except Exception:
        local_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        return local_dir

RUNTIME_DIR = _get_runtime_dir()
UPLOAD_DIR  = os.path.join(RUNTIME_DIR, "uploads")
SLIDES_DIR  = os.path.join(RUNTIME_DIR, "slides")
ALLOWED_EXT = {".ppt", ".pptx", ".pdf"}

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(SLIDES_DIR, exist_ok=True)

# Presentation state
state = {
    'current': 0,
    'total':   0,
    'loaded':  False,
    'title':   '',
}
state_lock = threading.Lock()


def clear_slides():
    """Remove all previously converted slide images."""
    if os.path.exists(SLIDES_DIR):
        for f in os.listdir(SLIDES_DIR):
            file_path = os.path.join(SLIDES_DIR, f)
            if os.path.isfile(file_path):
                try:
                    os.remove(file_path)
                except Exception:
                    pass


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
        pp = win32com.client.Dispatch("PowerPoint.Application")
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
    if not os.path.exists(SLIDES_DIR):
        return []
    return sorted(
        f for f in os.listdir(SLIDES_DIR) if f.endswith('.jpg')
    )


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
