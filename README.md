<div align="center">
  <img src="assets/banner.png" alt="Gesture PPT Controller Banner" width="100%" max-width="900px" style="border-radius: 10px; margin-bottom: 20px;">

  # Gesture PPT Controller

  **An AI-Powered Touchless Presentation Controller using Hand Gestures & Voice Recognition**

  [![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
  [![Flask](https://img.shields.io/badge/Framework-Flask-green.svg)](https://flask.palletsprojects.com/)
  [![MediaPipe](https://img.shields.io/badge/AI-MediaPipe-orange.svg)](https://mediapipe.dev/)
  [![OpenCV](https://img.shields.io/badge/CV-OpenCV-red.svg)](https://opencv.org/)
  [![License](https://img.shields.io/badge/License-MIT-brightgreen.svg)](#license)

</div>

---

## 📌 Overview

**Gesture PPT Controller** is a modern, touchless presentation control assistant designed to make slide navigation effortless and engaging. Using computer vision powered by **MediaPipe** and **OpenCV**, alongside **voice command recognition**, presenters can navigate slides, activate laser pointer tracking, annotate slides, and control playback completely hands-free without relying on clickers or physical hardware.

---

## ✨ Key Features

- 🖐️ **Real-Time Hand Gesture Control**
  - High-precision 21-landmark tracking using **MediaPipe GestureRecognizer** (VIDEO mode).
  - Smooth tracking for slide navigation, laser pointer, and annotation modes.
  - Automated skin-color contour fallback for lightweight operation.

- 🗣️ **Voice Command Recognition**
  - Integrated speech recognition for voice commands (`"Next"`, `"Previous"`, `"Start"`, `"Clear"`, etc.).
  - Cross-platform audio backend compatibility (`sounddevice`, `SpeechRecognition`).

- 📄 **PDF & PPTX Presentation Support**
  - Instant conversion of uploaded **PDF** documents via PyMuPDF (`fitz`).
  - Native **PPTX** slide rendering using Microsoft PowerPoint COM automation (`win32com.client`).

- 💻 **Interactive Web HUD & Live Dashboard**
  - Web-based interface built with Flask and responsive HTML5/CSS3/JS.
  - Real-time video preview with landmark visualization.
  - Slide thumbnail strip, slide counter, and interactive presentation status.

- ⚡ **One-Click Launch Script**
  - Convenient `start.bat` script for instant background process management, server initialization, and browser launching.

---

## 🎮 Controls & Commands

### 🖐️ Hand Gestures

| Gesture | Action |
| :--- | :--- |
| **Swipe Right / Open Palm Right** | Next Slide |
| **Swipe Left / Open Palm Left** | Previous Slide |
| **Index Point Finger** | Laser Pointer Mode |
| **Victory / Peace Sign (`V`)** | Toggle Drawing / Annotation Mode |
| **Closed Fist** | Pause Gesture Tracking / Freeze State |
| **Thumbs Up** | Jump to First Slide |

### 🗣️ Voice Commands

| Voice Command | Action |
| :--- | :--- |
| `"Next"` / `"Next Slide"` | Advance to next slide |
| `"Previous"` / `"Back"` | Go to previous slide |
| `"First"` / `"Start"` | Jump to beginning slide |
| `"Last"` / `"End"` | Jump to final slide |
| `"Clear"` | Clear active slide drawing annotations |

---

## 📁 Project Structure

```text
gesture-ppt-controller/
├── assets/
│   └── banner.png             # Project banner graphic
├── static/
│   └── slides/                # Rendered slide image cache (.jpg)
├── templates/
│   └── index.html             # Main Web Dashboard UI template
├── uploads/                   # Uploaded PDF / PPTX presentation files
├── app.py                     # Main Flask web app & Computer Vision engine
├── gesture_recognizer.task    # MediaPipe Gesture Recognizer ML Model
├── requirements.txt           # Python dependencies
├── start.bat                  # One-click startup script for Windows
└── README.md                  # Project documentation
```

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.9 – 3.11** installed on your system.
- Webcam and microphone connected.

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/DurgaPraveen07/smart_ppt_controller.git
   cd smart_ppt_controller
   ```

2. **Create and activate a virtual environment (recommended):**
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

### 🏃 Running the Application

- **Option A: Quick Start (Windows)**
  Double-click `start.bat` or run:
  ```cmd
  start.bat
  ```

- **Option B: Manual Start**
  Run the Flask server directly:
  ```bash
  python app.py
  ```

Open your browser and navigate to: **`http://localhost:5000`**

---

## 🛠️ Tech Stack

- **Backend**: Python, Flask, PyMuPDF (`fitz`), SpeechRecognition, `sounddevice`, `win32com.client`
- **Computer Vision**: OpenCV (`cv2`), MediaPipe (`mediapipe.tasks.python.vision`)
- **Frontend**: HTML5, CSS3, JavaScript (Fetch API, HTML5 Canvas)

---

## 📜 License

Distributed under the MIT License. See `LICENSE` for more information.