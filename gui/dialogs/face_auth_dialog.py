# gui/dialogs/face_auth_dialog.py
"""
Futuristic Biometric Face Authentication Dialog for Jarvis V2 Desktop.
Displays real-time optical scan, glowing biometric HUD, status telemetry,
and passcode fallback using native QtMultimedia with OpenCV fallback.
"""

import logging
import math
import sys
import time
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gui.dialogs.face_register_dialog import CameraThread
from security.face_authenticator import FaceAuthenticator

logger = logging.getLogger("jarvis.gui.face_auth")


class FaceAuthDialog(QDialog):
    """Futuristic PySide6 Biometric Authentication Window."""

    authenticated = Signal(bool, str)

    def __init__(self, authenticator: Optional[FaceAuthenticator] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.authenticator = authenticator or FaceAuthenticator()
        self.user_name = self.authenticator.user_name
        self.is_authenticated = False
        self.auth_method = ""

        self.setWindowTitle("JARVIS // Biometric Identity Gateway")
        self.setFixedSize(560, 680)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._current_frame = None
        self._scan_angle = 0
        self._confidence = 0.0
        self._start_time = time.time()
        self._timeout = self.authenticator.timeout_seconds
        self._qcamera = None
        self._session = None
        self._sink = None
        self.camera_thread = None
        self._consecutive_matches = 0
        self._required_consecutive_matches = 3
        self._low_light_mode = False
        self._fill_light_active = False
        self._is_verifying = False
        self._last_verify_time = 0.0
        self._verify_interval = 0.12  # Run biometric verification at smooth ~8 FPS rate

        self._init_ui()
        self._start_camera_stream()

        # Update timer for HUD animation & timeout check
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_anim_tick)
        self.timer.start(40)  # ~25 FPS

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)

        # Container Card with glowing border
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
        title_label = QLabel("JARVIS SECURITY GATEWAY")
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
        sub_label = QLabel(f"Biometric Verification Required for: {self.user_name}")
        sub_label.setFont(QFont("Segoe UI", 10, QFont.DemiBold))
        sub_label.setStyleSheet("color: #94a3b8; border: none;")
        card_layout.addWidget(sub_label)

        # Video Viewport
        self.video_label = QLabel(self)
        self.video_label.setFixedSize(480, 320)
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet("""
            QLabel {
                background-color: #060a12;
                border: 2px solid #00f2fe;
                border-radius: 12px;
                color: #00f2fe;
            }
        """)
        card_layout.addWidget(self.video_label, alignment=Qt.AlignCenter)

        # Telemetry / Status Label
        self.status_label = QLabel("Connecting to optical sensor...")
        self.status_label.setFont(QFont("Segoe UI", 10))
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #cbd5e1; border: none;")
        card_layout.addWidget(self.status_label)

        # Progress bar
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #1e293b;
                border-radius: 4px;
                border: none;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4facfe, stop:1 #00f2fe);
                border-radius: 4px;
            }
        """)
        card_layout.addWidget(self.progress_bar)

        # Passcode fallback container
        self.pin_container = QWidget(self)
        self.pin_container.setStyleSheet("border: none; background: transparent;")
        pin_layout = QHBoxLayout(self.pin_container)
        pin_layout.setContentsMargins(0, 5, 0, 0)

        self.pin_input = QLineEdit(self)
        self.pin_input.setPlaceholderText("Enter Master PIN (Fallback)...")
        self.pin_input.setEchoMode(QLineEdit.Password)
        self.pin_input.setFixedHeight(36)
        self.pin_input.setStyleSheet("""
            QLineEdit {
                background-color: #111827;
                border: 1px solid #334155;
                border-radius: 8px;
                color: #f8fafc;
                padding-left: 12px;
                font-size: 11px;
            }
            QLineEdit:focus {
                border: 1px solid #00f2fe;
            }
        """)
        self.pin_input.returnPressed.connect(self._verify_pin)

        self.fill_light_btn = QPushButton("🌙 Fill Light")
        self.fill_light_btn.setFixedHeight(36)
        self.fill_light_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #94a3b8;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 0 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #334155;
                color: #f8fafc;
            }
        """)
        self.fill_light_btn.clicked.connect(self._toggle_fill_light)

        self.retry_btn = QPushButton("↻ Retry")
        self.retry_btn.setFixedHeight(36)
        self.retry_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #38bdf8;
                border: 1px solid #0284c7;
                border-radius: 8px;
                padding: 0 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0284c7;
                color: #ffffff;
            }
        """)
        self.retry_btn.clicked.connect(self._retry_scan)

        self.unlock_btn = QPushButton("Unlock with PIN")
        self.unlock_btn.setFixedHeight(36)
        self.unlock_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #00f2fe;
                border: 1px solid #00f2fe;
                border-radius: 8px;
                padding: 0 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #00f2fe;
                color: #0d1322;
            }
        """)
        self.unlock_btn.clicked.connect(self._verify_pin)

        pin_layout.addWidget(self.pin_input)
        pin_layout.addWidget(self.fill_light_btn)
        pin_layout.addWidget(self.retry_btn)
        pin_layout.addWidget(self.unlock_btn)
        card_layout.addWidget(self.pin_container)

        main_layout.addWidget(self.card)
        self.pin_input.setFocus()

    def _toggle_fill_light(self):
        """Toggles virtual soft fill-light to illuminate user's face in dark environments."""
        self._fill_light_active = not self._fill_light_active
        if self._fill_light_active:
            self.card.setStyleSheet("""
                QFrame {
                    background-color: #f8fafc;
                    border: 3px solid #38bdf8;
                    border-radius: 16px;
                }
            """)
            self.fill_light_btn.setText("☀️ Light ON")
            self.fill_light_btn.setStyleSheet("""
                QPushButton {
                    background-color: #38bdf8;
                    color: #0f172a;
                    border: 1px solid #38bdf8;
                    border-radius: 8px;
                    padding: 0 12px;
                    font-weight: bold;
                }
            """)
        else:
            self.card.setStyleSheet("""
                QFrame {
                    background-color: #0d1322;
                    border: 2px solid #00f2fe;
                    border-radius: 16px;
                }
            """)
            self.fill_light_btn.setText("🌙 Fill Light")
            self.fill_light_btn.setStyleSheet("""
                QPushButton {
                    background-color: #1e293b;
                    color: #94a3b8;
                    border: 1px solid #334155;
                    border-radius: 8px;
                    padding: 0 12px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #334155;
                    color: #f8fafc;
                }
            """)

    def _retry_scan(self):
        """Resets the biometric scan timer and resumes active face scanning."""
        self._start_time = time.time()
        self._consecutive_matches = 0
        self._is_verifying = False
        self._current_frame = None
        self.status_label.setText("Sensor active! Scanning biometrics...")
        self.status_label.setStyleSheet("color: #00f2fe; border: none;")
        if hasattr(self, "_qcamera") and self._qcamera:
            if not self._qcamera.isActive():
                try:
                    self._qcamera.start()
                except Exception:
                    pass
        elif not self.camera_thread or not self.camera_thread.isRunning():
            self._start_camera_stream()
        self.pin_input.setFocus()

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
                self._qcamera.errorOccurred.connect(self._on_camera_error)
                self._qcamera.start()
                self.status_label.setText(f"Sensor active ({target_dev.description()})! Scanning biometrics...")
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
            self.status_label.setText(f"Camera notice: {e}")

    def _on_camera_error(self, error, error_string=""):
        logger.warning("Camera hardware error: %s (%s)", error, error_string)
        self.status_label.setText("Camera sensor standby. Enter Master PIN or click Retry.")
        self.status_label.setStyleSheet("color: #f59e0b; border: none;")
        self.pin_input.setFocus()

    def _on_qt_video_frame(self, vframe):
        if not vframe.isValid() or self.is_authenticated:
            return
        img = vframe.toImage()
        if img.isNull():
            return
        self._on_frame_received(img)

    def _on_camera_status(self, connected: bool, message: str):
        if not self._current_frame:
            if connected:
                self.status_label.setText(message)
                self.status_label.setStyleSheet("color: #cbd5e1; border: none;")
            else:
                self.status_label.setText("Optical sensor unavailable. Enter Master PIN or voice passphrase:")
                self.status_label.setStyleSheet("color: #f59e0b; border: none;")
                self.pin_input.setFocus()

    def _on_frame_received(self, frame):
        if self.is_authenticated:
            return

        self._current_frame = frame
        self._render_frame(frame)

        # Re-entrancy protection to prevent frame queue accumulation
        if self._is_verifying:
            return

        self._is_verifying = True
        try:
            # Scaled copy for instantaneous verification calculation
            if isinstance(frame, QImage) and (frame.width() > 480 or frame.height() > 360):
                verify_input = frame.scaled(320, 240, Qt.KeepAspectRatio, Qt.FastTransformation)
            else:
                verify_input = frame

            success, conf, msg = self.authenticator.verify_frame(verify_input)
            self._confidence = conf
            self.progress_bar.setValue(int(conf * 100))

            # Check if currently timed out and still searching
            is_timed_out = (time.time() - self._start_time > self._timeout)
            if success and conf >= self.authenticator.confidence_threshold:
                self._consecutive_matches += 1
                if self._consecutive_matches >= self._required_consecutive_matches:
                    self._on_auth_success("facial_biometrics", f"Welcome back, {self.user_name}!")
                    return
            else:
                self._consecutive_matches = 0

            if not is_timed_out:
                self.status_label.setText(msg)
                if "Identity Confirmed" in msg:
                    self.status_label.setStyleSheet("color: #10b981; border: none;")
                elif "Analyzing" in msg:
                    self.status_label.setStyleSheet("color: #00f2fe; border: none;")
                elif "Low light" in msg or "Low-Light" in msg:
                    self.status_label.setStyleSheet("color: #f59e0b; border: none; font-weight: bold;")
                else:
                    self.status_label.setStyleSheet("color: #cbd5e1; border: none;")
        finally:
            self._is_verifying = False

    def _on_anim_tick(self):
        self._scan_angle = (self._scan_angle + 6) % 360

        if self._current_frame is None and not self.is_authenticated:
            self._render_placeholder()

        # Camera frame watchdog (if no frame arrived after 3.0s)
        if not self.is_authenticated and self._current_frame is None and (time.time() - self._start_time > 3.0):
            if not self.status_label.text().startswith("Camera sensor standby"):
                self.status_label.setText("Camera sensor standby. Enter Master PIN or click Retry.")
                self.status_label.setStyleSheet("color: #f59e0b; border: none;")

        # Check timeout notice
        if not self.is_authenticated and (time.time() - self._start_time > self._timeout):
            if "Biometric Scan timed out" not in self.status_label.text() and not self.is_authenticated:
                self.status_label.setText("Biometric Scan timed out. Use Master PIN or click Retry.")
                self.status_label.setStyleSheet("color: #f59e0b; border: none;")

    def _render_frame(self, frame):
        try:
            if isinstance(frame, QImage):
                pixmap = QPixmap.fromImage(frame).scaled(480, 320, Qt.KeepAspectRatioByExpanding, Qt.FastTransformation)
            else:
                import cv2
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb.shape
                bytes_per_line = ch * w
                q_img = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
                pixmap = QPixmap.fromImage(q_img).scaled(480, 320, Qt.KeepAspectRatioByExpanding, Qt.FastTransformation)

            # Draw glowing HUD reticle over frame
            painter = QPainter(pixmap)
            if painter.isActive():
                painter.setRenderHint(QPainter.Antialiasing)
                pen = QPen(QColor(0, 242, 254, 180), 2, Qt.DashLine)
                painter.setPen(pen)

                cx, cy = pixmap.width() // 2, pixmap.height() // 2
                painter.drawEllipse(cx - 70, cy - 70, 140, 140)
                painter.end()

            self.video_label.setPixmap(pixmap)
        except Exception:
            pass

    def _render_placeholder(self):
        pixmap = QPixmap(480, 320)
        pixmap.fill(QColor("#060a12"))
        painter = QPainter(pixmap)
        if painter.isActive():
            painter.setRenderHint(QPainter.Antialiasing)

            # Draw glowing radar scan
            pen = QPen(QColor(0, 242, 254, 140), 2)
            painter.setPen(pen)
            cx, cy = 240, 160
            painter.drawEllipse(cx - 60, cy - 60, 120, 120)
            painter.drawEllipse(cx - 30, cy - 30, 60, 60)

            # Rotating scanner beam
            rad = math.radians(self._scan_angle)
            bx = cx + int(60 * math.cos(rad))
            by = cy + int(60 * math.sin(rad))
            painter.setPen(QPen(QColor("#00f2fe"), 3))
            painter.drawLine(cx, cy, bx, by)

            painter.setPen(QPen(QColor("#64748b")))
            painter.setFont(QFont("Segoe UI", 9))
            painter.drawText(0, 260, 480, 30, Qt.AlignCenter, "[ BIOMETRIC RADAR SCANNING ]")
            painter.end()

        self.video_label.setPixmap(pixmap)

    def _verify_pin(self):
        val = self.pin_input.text().strip()
        auth_res = self.authenticator.authenticate_voice_pin(val)
        if auth_res.success:
            self._on_auth_success(auth_res.method, auth_res.message or f"PIN Accepted! Welcome, {self.user_name}!")
        else:
            self.status_label.setText(auth_res.error or "Incorrect PIN. Access Denied.")
            self.status_label.setStyleSheet("color: #ef4444; border: none;")
            self.pin_input.clear()

    def _on_auth_success(self, method: str, message: str):
        self._cleanup()
        self.is_authenticated = True
        self.auth_method = method
        self.status_label.setText(message)
        self.status_label.setStyleSheet("color: #10b981; font-weight: bold; border: none;")
        self.progress_bar.setValue(100)

        # Brief smooth confirmation then accept
        QTimer.singleShot(150, self.accept)
        self.authenticated.emit(True, method)

    def _cleanup(self):
        if hasattr(self, "timer") and self.timer.isActive():
            self.timer.stop()
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
