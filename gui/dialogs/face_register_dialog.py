# gui/dialogs/face_register_dialog.py
"""
Futuristic Face Registration and Biometric Profile Enrollment Dialog for Jarvis V2.
Allows the user to view live camera stream, check face alignment, and capture/register
their biometric profile seamlessly from the GUI using native QtMultimedia with OpenCV fallback.
"""

import logging
import math
import sys
import time
from typing import Optional

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from security.face_authenticator import FaceAuthenticator

logger = logging.getLogger("jarvis.gui.face_register")


class CameraThread(QThread):
    """Fallback background worker thread for OpenCV frame capture when QtMultimedia is unavailable."""

    frame_ready = Signal(object)
    status_changed = Signal(bool, str)

    def __init__(self, camera_index: int = 0, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.camera_index = camera_index
        self._running = True

    def run(self):
        try:
            import cv2

            cap = None
            if hasattr(cv2, "CAP_DSHOW"):
                try:
                    cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
                    if not cap.isOpened():
                        cap = None
                except Exception:
                    cap = None

            if not cap or not cap.isOpened():
                try:
                    cap = cv2.VideoCapture(self.camera_index)
                except Exception:
                    cap = None

            if not cap or not cap.isOpened():
                for alt_idx in (1, 0, 2):
                    if alt_idx == self.camera_index:
                        continue
                    try:
                        cap = cv2.VideoCapture(alt_idx, getattr(cv2, "CAP_DSHOW", cv2.CAP_ANY))
                        if cap.isOpened():
                            break
                    except Exception:
                        continue

            if not cap or not cap.isOpened():
                self.status_changed.emit(False, "Camera not found. Please check webcam connection.")
                return

            try:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:
                pass

            self.status_changed.emit(True, "Camera connected! Looking for face...")

            while self._running:
                ret, frame = cap.read()
                if ret and frame is not None:
                    self.frame_ready.emit(frame)
                else:
                    time.sleep(0.02)

            cap.release()
        except Exception as e:
            logger.debug("OpenCV CameraThread exception: %s", e)
            self.status_changed.emit(False, f"Camera error: {e}")

    def stop(self):
        self._running = False
        self.wait(1000)


class FaceRegisterDialog(QDialog):
    """Futuristic PySide6 Biometric Face Registration Window."""

    enrolled = Signal(bool, str)

    def __init__(self, authenticator: Optional[FaceAuthenticator] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.authenticator = authenticator or FaceAuthenticator()
        self.user_name = self.authenticator.user_name
        self.is_enrolled = False

        self.setWindowTitle("JARVIS // Biometric Profile Registration")
        self.setFixedSize(580, 720)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._current_frame = None
        self._scan_angle = 0
        self._countdown = 0
        self._has_face = False
        self._face_box = None
        self._qcamera = None
        self._session = None
        self._sink = None
        self.camera_thread = None

        self._init_ui()
        self._start_camera_stream()

        # Radar animation timer for placeholder when camera is starting up
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._on_anim_tick)
        self.anim_timer.start(40)

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)

        self.card = QFrame(self)
        self.card.setStyleSheet("""
            QFrame {
                background-color: #0d1322;
                border: 2px solid #00f2fe;
                border-radius: 16px;
            }
        """)
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(25, 25, 25, 25)
        card_layout.setSpacing(14)

        # Header Title
        header_layout = QHBoxLayout()
        title_label = QLabel("BIOMETRIC REGISTRATION")
        title_label.setFont(QFont("Segoe UI", 12, QFont.Bold))
        title_label.setStyleSheet("color: #00f2fe; border: none; letter-spacing: 2px;")

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #8892b0;
                font-size: 14px;
                border: 1px solid #1e293b;
                border-radius: 14px;
            }
            QPushButton:hover {
                color: #ff5555;
                border: 1px solid #ff5555;
            }
        """)
        close_btn.clicked.connect(self.reject)

        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(close_btn)
        card_layout.addLayout(header_layout)

        # Subtitle
        sub_label = QLabel("Position your face within the reticle and click Register Face")
        sub_label.setFont(QFont("Segoe UI", 9))
        sub_label.setStyleSheet("color: #64748b; border: none;")
        card_layout.addWidget(sub_label)

        # Name Input Row
        name_row = QHBoxLayout()
        name_lbl = QLabel("User Name:")
        name_lbl.setStyleSheet("color: #cbd5e1; font-weight: bold; border: none;")
        self.name_input = QLineEdit(self.user_name)
        self.name_input.setFixedHeight(34)
        self.name_input.setStyleSheet("""
            QLineEdit {
                background-color: #111827;
                border: 1px solid #334155;
                border-radius: 8px;
                color: #f8fafc;
                padding-left: 10px;
                font-weight: 600;
            }
            QLineEdit:focus {
                border: 1px solid #00f2fe;
            }
        """)
        name_row.addWidget(name_lbl)
        name_row.addWidget(self.name_input)
        card_layout.addLayout(name_row)

        # Video Viewport
        self.video_label = QLabel(self)
        self.video_label.setFixedSize(500, 330)
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet("""
            QLabel {
                background-color: #060a12;
                border: 2px dashed #00f2fe;
                border-radius: 12px;
                color: #00f2fe;
            }
        """)
        card_layout.addWidget(self.video_label, alignment=Qt.AlignCenter)

        # Status & Quality Indicator
        self.status_label = QLabel("Connecting to optical camera...")
        self.status_label.setFont(QFont("Segoe UI", 10, QFont.DemiBold))
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #f59e0b; border: none;")
        card_layout.addWidget(self.status_label)

        # Action Buttons
        btn_layout = QHBoxLayout()
        self.register_btn = QPushButton("📷  Capture & Register Face")
        self.register_btn.setFixedHeight(40)
        self.register_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00c6ff, stop:1 #0072ff);
                color: #ffffff;
                font-weight: bold;
                font-size: 12px;
                border: none;
                border-radius: 8px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00f2fe, stop:1 #4facfe);
            }
            QPushButton:disabled {
                background-color: #334155;
                color: #64748b;
            }
        """)
        self.register_btn.clicked.connect(self._start_capture)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setFixedHeight(40)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #94a3b8;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 0 16px;
            }
            QPushButton:hover {
                background-color: #334155;
                color: #f8fafc;
            }
        """)
        self.cancel_btn.clicked.connect(self.reject)

        btn_layout.addWidget(self.register_btn, stretch=2)
        btn_layout.addWidget(self.cancel_btn, stretch=1)
        card_layout.addLayout(btn_layout)

        main_layout.addWidget(self.card)

    def _start_camera_stream(self):
        """Starts live video stream using PySide6 QtMultimedia (Primary) with OpenCV fallback."""
        # 1. Primary Engine: Native QtMultimedia
        try:
            from PySide6.QtMultimedia import QCamera, QMediaCaptureSession, QMediaDevices, QVideoSink

            video_inputs = QMediaDevices.videoInputs()
            if video_inputs:
                target_dev = video_inputs[0]
                self._qcamera = QCamera(target_dev, self)
                self._session = QMediaCaptureSession(self)
                self._sink = QVideoSink(self)
                self._session.setCamera(self._qcamera)
                self._session.setVideoSink(self._sink)
                self._sink.videoFrameChanged.connect(self._on_qt_video_frame)
                self._qcamera.start()
                self.status_label.setText(f"Camera active ({target_dev.description()})! Looking for face...")
                self.status_label.setStyleSheet("color: #10b981; border: none;")
                return
        except Exception as e:
            logger.debug("QtMultimedia initialization skipped: %s", e)

        # 2. Fallback Engine: Dedicated OpenCV CameraThread
        try:
            self.camera_thread = CameraThread(camera_index=self.authenticator.camera_index, parent=self)
            self.camera_thread.frame_ready.connect(self._on_frame_received)
            self.camera_thread.status_changed.connect(self._on_camera_status)
            self.camera_thread.start()
        except Exception as e:
            self.status_label.setText(f"Camera initialization notice: {e}")
            self.status_label.setStyleSheet("color: #f59e0b; border: none;")

    def _on_qt_video_frame(self, vframe):
        if not vframe.isValid():
            return
        img = vframe.toImage()
        if img.isNull():
            return
        self._on_frame_received(img)

    def _on_camera_status(self, connected: bool, message: str):
        if not self._current_frame:
            self.status_label.setText(message)
            self.status_label.setStyleSheet("color: #10b981; border: none;" if connected else "color: #ef4444; border: none;")

    def _on_frame_received(self, frame):
        self._current_frame = frame
        self._has_face, self._face_box = self.authenticator.detect_face_in_frame(frame)

        if self._countdown > 0:
            self.status_label.setText(f"Capturing face in {self._countdown}...")
            self.status_label.setStyleSheet("color: #00f2fe; font-weight: bold; border: none;")
        elif self._has_face:
            self.status_label.setText("Face detected! Ready to register.")
            self.status_label.setStyleSheet("color: #10b981; border: none;")
        else:
            self.status_label.setText("Looking for face... Please look directly at the camera.")
            self.status_label.setStyleSheet("color: #94a3b8; border: none;")

        self._render_frame(frame)

    def _on_anim_tick(self):
        self._scan_angle = (self._scan_angle + 6) % 360
        if self._current_frame is None:
            self._render_placeholder()

    def _render_frame(self, frame):
        try:
            if isinstance(frame, QImage):
                pixmap = QPixmap.fromImage(frame).scaled(500, 330, Qt.KeepAspectRatioByExpanding, Qt.FastTransformation)
            else:
                import cv2
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb.shape
                bytes_per_line = ch * w
                q_img = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
                pixmap = QPixmap.fromImage(q_img).scaled(500, 330, Qt.KeepAspectRatioByExpanding, Qt.FastTransformation)

            painter = QPainter(pixmap)
            if painter.isActive():
                painter.setRenderHint(QPainter.Antialiasing)
                cx, cy = pixmap.width() // 2, pixmap.height() // 2

                # Reticle color depends on whether face is detected
                color = QColor(16, 185, 129, 200) if self._has_face else QColor(0, 242, 254, 180)
                pen = QPen(color, 2, Qt.DashLine)
                painter.setPen(pen)
                painter.drawEllipse(cx - 75, cy - 75, 150, 150)

                # Draw corner brackets
                painter.setPen(QPen(QColor(0, 242, 254), 3))
                offset = 85
                painter.drawLine(cx - offset, cy - offset, cx - offset + 20, cy - offset)
                painter.drawLine(cx - offset, cy - offset, cx - offset, cy - offset + 20)
                painter.drawLine(cx + offset, cy - offset, cx + offset - 20, cy - offset)
                painter.drawLine(cx + offset, cy - offset, cx + offset, cy - offset + 20)
                painter.drawLine(cx - offset, cy + offset, cx - offset + 20, cy + offset)
                painter.drawLine(cx - offset, cy + offset, cx - offset, cy + offset - 20)
                painter.drawLine(cx + offset, cy + offset, cx + offset - 20, cy + offset)
                painter.drawLine(cx + offset, cy + offset, cx + offset, cy + offset - 20)

                if self._countdown > 0:
                    painter.setPen(QPen(QColor("#00f2fe")))
                    painter.setFont(QFont("Segoe UI", 36, QFont.Bold))
                    painter.drawText(0, 0, pixmap.width(), pixmap.height(), Qt.AlignCenter, str(self._countdown))

                painter.end()

            self.video_label.setPixmap(pixmap)
        except Exception as e:
            logger.debug("Render frame exception: %s", e)

    def _render_placeholder(self):
        pixmap = QPixmap(500, 330)
        pixmap.fill(QColor("#060a12"))
        painter = QPainter(pixmap)
        if painter.isActive():
            painter.setRenderHint(QPainter.Antialiasing)

            pen = QPen(QColor(0, 242, 254, 140), 2)
            painter.setPen(pen)
            cx, cy = 250, 165
            painter.drawEllipse(cx - 60, cy - 60, 120, 120)

            rad = math.radians(self._scan_angle)
            bx = cx + int(60 * math.cos(rad))
            by = cy + int(60 * math.sin(rad))
            painter.setPen(QPen(QColor("#00f2fe"), 3))
            painter.drawLine(cx, cy, bx, by)

            painter.setPen(QPen(QColor("#64748b")))
            painter.setFont(QFont("Segoe UI", 9))
            painter.drawText(0, 260, 500, 30, Qt.AlignCenter, "[ WAITING FOR CAMERA STREAM ]")
            painter.end()

        self.video_label.setPixmap(pixmap)

    def _start_capture(self):
        target_name = self.name_input.text().strip() or self.user_name

        if self._current_frame is None:
            for _ in range(10):
                time.sleep(0.05)
                if self._current_frame is not None:
                    break

        if self._current_frame is None:
            self.status_label.setText("Waiting for live camera frame... Please look at the camera.")
            self.status_label.setStyleSheet("color: #f59e0b; border: none;")
            return

        # Perform registration directly with current live frame
        res = self.authenticator.enroll(frame=self._current_frame, user_name=target_name)

        if res.get("success"):
            self.is_enrolled = True
            self.status_label.setText(f"✓ Face successfully registered for {target_name}!")
            self.status_label.setStyleSheet("color: #10b981; font-weight: bold; border: none;")
            self.register_btn.setEnabled(False)
            self.name_input.setEnabled(False)
            self.enrolled.emit(True, target_name)
            QTimer.singleShot(1200, self.accept)
        else:
            self.status_label.setText(f"Registration error: {res.get('error', 'Capture failed')}")
            self.status_label.setStyleSheet("color: #ef4444; border: none;")

    def _cleanup(self):
        if hasattr(self, "anim_timer") and self.anim_timer.isActive():
            self.anim_timer.stop()
        if hasattr(self, "_qcamera") and self._qcamera:
            try:
                self._qcamera.stop()
            except Exception:
                pass
        if hasattr(self, "camera_thread") and self.camera_thread and self.camera_thread.isRunning():
            self.camera_thread.stop()

    def closeEvent(self, event):
        self._cleanup()
        super().closeEvent(event)

    def reject(self):
        self._cleanup()
        super().reject()

    def accept(self):
        self._cleanup()
        super().accept()
