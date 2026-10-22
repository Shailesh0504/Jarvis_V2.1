# plugins/camera/plugin.py
"""Camera capability plugin implementation for webcam capture, recording, and image analysis."""

import datetime
import logging
import os
import subprocess
import time
from typing import Any, Dict, List, Optional

from plugins.base import BasePlugin
from plugins.manifest import PluginManifest, PluginResult
from .commands import ACTIONS
from .permissions import PERMISSIONS_REQUIRED

logger = logging.getLogger("jarvis.plugins.camera")

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None


class CameraPlugin(BasePlugin):
    """Controls webcam capture, video recording, image filters, and computer vision utilities."""

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="camera",
            version="2.0.0",
            description="Webcam photo capture, video recording, image filters, and vision utilities.",
            author="Jarvis Team",
            permissions=PERMISSIONS_REQUIRED,
            actions=ACTIONS
        )

    def verify_state(self, action_name: str, parameters: Dict[str, Any], result_data: Any) -> Optional[Any]:
        from core.execution.models import VerificationResult, ExecutionState
        if action_name in ("capture_photo", "record_video_clip", "apply_camera_filter", "generate_test_pattern"):
            path = (result_data or {}).get("path") or (result_data or {}).get("save_path")
            if path and os.path.isfile(path) and os.path.getsize(path) > 0:
                return VerificationResult(
                    verified=True,
                    state=ExecutionState.SUCCESS,
                    check_type="file_exists",
                    expected=path,
                    actual=f"{os.path.getsize(path)} bytes",
                    message="Camera output artifact verified on disk."
                )
            return VerificationResult(
                verified=False,
                state=ExecutionState.FAILED,
                check_type="file_exists",
                expected=path or "valid file",
                actual="File missing or empty",
                error="Expected camera file was not generated."
            )
        return None

    def execute(self, action_name: str, parameters: Optional[Dict[str, Any]] = None) -> PluginResult:
        parameters = parameters or {}

        # 1. capture_photo
        if action_name == "capture_photo":
            if not cv2:
                return PluginResult(success=False, error="OpenCV (cv2) library is not available.")

            idx = int(parameters.get("device_index", 0))
            path = parameters.get("save_path", "").strip()
            if not path:
                os.makedirs("data/camera", exist_ok=True)
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                path = os.path.join("data", "camera", f"camera_snap_{ts}.jpg")
            else:
                os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

            cap = cv2.VideoCapture(idx)
            if not cap.isOpened():
                return PluginResult(success=False, error=f"Could not open camera device index {idx}.")

            try:
                ret, frame = cap.read()
                if not ret or frame is None:
                    return PluginResult(success=False, error="Failed to grab frame from camera.")
                cv2.imwrite(path, frame)
                h, w, _ = frame.shape
                return PluginResult(
                    success=True,
                    data={"path": os.path.abspath(path), "width": w, "height": h, "message": f"Photo saved: {path} ({w}x{h})."}
                )
            finally:
                cap.release()

        # 2. open_camera_app
        elif action_name == "open_camera_app":
            try:
                subprocess.Popen("start microsoft.windows.camera:", shell=True)
                return PluginResult(
                    success=True,
                    data={"message": "Windows Camera application open kar di hai, Boss."}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Camera app launch error: {e}")

        # 3. record_video_clip
        elif action_name == "record_video_clip":
            if not cv2:
                return PluginResult(success=False, error="OpenCV is required for video recording.")

            idx = int(parameters.get("device_index", 0))
            duration = max(1, min(30, int(parameters.get("duration_seconds", 5))))
            path = parameters.get("save_path", "").strip()
            if not path:
                os.makedirs("data/camera", exist_ok=True)
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                path = os.path.join("data", "camera", f"clip_{ts}.avi")
            else:
                os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

            cap = cv2.VideoCapture(idx)
            if not cap.isOpened():
                return PluginResult(success=False, error=f"Cannot open camera device {idx}.")

            try:
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
                fps = 20.0
                fourcc = cv2.VideoWriter_fourcc(*'XVID')
                out = cv2.VideoWriter(path, fourcc, fps, (w, h))

                frames_to_record = int(fps * duration)
                written = 0
                for _ in range(frames_to_record):
                    ret, frame = cap.read()
                    if not ret:
                        break
                    out.write(frame)
                    written += 1
                out.release()

                return PluginResult(
                    success=True,
                    data={
                        "path": os.path.abspath(path),
                        "frames": written,
                        "duration_sec": duration,
                        "message": f"Recorded video clip ({duration}s, {written} frames) to {path}."
                    }
                )
            finally:
                cap.release()

        # 4. capture_burst_photos
        elif action_name == "capture_burst_photos":
            if not cv2:
                return PluginResult(success=False, error="OpenCV is required.")

            idx = int(parameters.get("device_index", 0))
            out_dir = parameters.get("output_dir", "data/camera").strip()
            count = max(1, min(10, int(parameters.get("count", 3))))
            interval = max(0.1, float(parameters.get("interval_seconds", 0.5)))
            os.makedirs(out_dir, exist_ok=True)

            cap = cv2.VideoCapture(idx)
            if not cap.isOpened():
                return PluginResult(success=False, error=f"Cannot open camera device {idx}.")

            saved_paths = []
            try:
                for i in range(count):
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                        fp = os.path.join(out_dir, f"burst_{ts}_{i+1}.jpg")
                        cv2.imwrite(fp, frame)
                        saved_paths.append(os.path.abspath(fp))
                    if i < count - 1:
                        time.sleep(interval)

                return PluginResult(
                    success=True,
                    data={"count": len(saved_paths), "paths": saved_paths, "message": f"Captured {len(saved_paths)} burst photos in {out_dir}."}
                )
            finally:
                cap.release()

        # 5. list_camera_devices
        elif action_name == "list_camera_devices":
            if not cv2:
                return PluginResult(success=False, error="OpenCV is required.")

            max_probe = max(1, min(10, int(parameters.get("max_devices_to_probe", 4))))
            available = []
            for i in range(max_probe):
                cap = cv2.VideoCapture(i)
                if cap.isOpened():
                    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    available.append({"index": i, "status": "available", "resolution": f"{w}x{h}"})
                    cap.release()

            return PluginResult(
                success=True,
                data={"available_devices": available, "count": len(available), "message": f"Detected {len(available)} accessible camera device(s)."}
            )

        # 6. get_camera_resolution
        elif action_name == "get_camera_resolution":
            if not cv2:
                return PluginResult(success=False, error="OpenCV is required.")

            idx = int(parameters.get("device_index", 0))
            cap = cv2.VideoCapture(idx)
            if not cap.isOpened():
                return PluginResult(success=False, error=f"Camera device {idx} unavailable.")

            try:
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = cap.get(cv2.CAP_PROP_FPS)
                return PluginResult(
                    success=True,
                    data={"device_index": idx, "width": w, "height": h, "fps": fps, "message": f"Camera {idx} resolution: {w}x{h} @ {fps:.1f} FPS."}
                )
            finally:
                cap.release()

        # 7. capture_motion_snapshot
        elif action_name == "capture_motion_snapshot":
            if not cv2 or np is None:
                return PluginResult(success=False, error="OpenCV and numpy are required.")

            idx = int(parameters.get("device_index", 0))
            thresh_val = int(parameters.get("threshold", 25))
            path = parameters.get("save_path", "").strip()

            cap = cv2.VideoCapture(idx)
            if not cap.isOpened():
                return PluginResult(success=False, error=f"Camera device {idx} unavailable.")

            try:
                ret1, frame1 = cap.read()
                time.sleep(0.3)
                ret2, frame2 = cap.read()

                if not ret1 or not ret2:
                    return PluginResult(success=False, error="Failed grabbing frames for motion comparison.")

                gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
                gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)
                diff = cv2.absdiff(gray1, gray2)
                _, thresh = cv2.threshold(diff, thresh_val, 255, cv2.THRESH_BINARY)
                motion_pixels = int(np.count_nonzero(thresh))
                motion_detected = motion_pixels > 500

                saved_path = None
                if motion_detected:
                    if not path:
                        os.makedirs("data/camera", exist_ok=True)
                        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                        path = os.path.join("data", "camera", f"motion_alert_{ts}.jpg")
                    cv2.imwrite(path, frame2)
                    saved_path = os.path.abspath(path)

                return PluginResult(
                    success=True,
                    data={
                        "motion_detected": motion_detected,
                        "delta_pixels": motion_pixels,
                        "saved_path": saved_path,
                        "message": f"Motion detected ({motion_pixels} pixels changed)!" if motion_detected else "No significant motion detected."
                    }
                )
            finally:
                cap.release()

        # 8. apply_camera_filter
        elif action_name == "apply_camera_filter":
            if not cv2 or np is None:
                return PluginResult(success=False, error="OpenCV is required.")

            img_path = parameters.get("image_path", "").strip()
            filter_type = parameters.get("filter_type", "grayscale").strip().lower()
            save_path = parameters.get("save_path", "").strip()

            if not img_path or not os.path.isfile(img_path):
                return PluginResult(success=False, error=f"Image path '{img_path}' not found.")

            frame = cv2.imread(img_path)
            if frame is None:
                return PluginResult(success=False, error="Could not read image file.")

            if filter_type == "grayscale":
                filtered = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            elif filter_type == "blur":
                filtered = cv2.GaussianBlur(frame, (15, 15), 0)
            elif filter_type == "edges":
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                filtered = cv2.Canny(gray, 100, 200)
            elif filter_type == "invert":
                filtered = cv2.bitwise_not(frame)
            elif filter_type == "sepia":
                kernel = np.array([[0.272, 0.534, 0.131],
                                   [0.349, 0.686, 0.168],
                                   [0.393, 0.769, 0.189]])
                filtered = cv2.transform(frame, kernel)
                filtered = np.clip(filtered, 0, 255).astype(np.uint8)
            else:
                return PluginResult(success=False, error=f"Unsupported filter '{filter_type}'. Use grayscale, blur, edges, sepia, invert.")

            if not save_path:
                root, ext = os.path.splitext(img_path)
                save_path = f"{root}_{filter_type}{ext or '.png'}"

            os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
            cv2.imwrite(save_path, filtered)

            return PluginResult(
                success=True,
                data={"path": os.path.abspath(save_path), "filter": filter_type, "message": f"Applied '{filter_type}' filter and saved to {save_path}."}
            )

        # 9. detect_qr_code
        elif action_name == "detect_qr_code":
            if not cv2:
                return PluginResult(success=False, error="OpenCV is required.")

            img_path = parameters.get("image_path", "").strip()
            detector = cv2.QRCodeDetector()

            if img_path and os.path.isfile(img_path):
                img = cv2.imread(img_path)
                if img is None:
                    return PluginResult(success=False, error=f"Could not load image '{img_path}'.")
                val, points, _ = detector.detectAndDecode(img)
                return PluginResult(
                    success=True,
                    data={"found": bool(val), "data": val or "", "message": f"QR Code found: '{val}'" if val else "No QR code detected in image."}
                )
            else:
                # Live capture from camera
                idx = int(parameters.get("device_index", 0))
                cap = cv2.VideoCapture(idx)
                if not cap.isOpened():
                    return PluginResult(success=False, error=f"Camera {idx} unavailable.")
                try:
                    ret, frame = cap.read()
                    if not ret:
                        return PluginResult(success=False, error="Failed to grab live frame.")
                    val, points, _ = detector.detectAndDecode(frame)
                    return PluginResult(
                        success=True,
                        data={"found": bool(val), "data": val or "", "message": f"QR Code: '{val}'" if val else "No QR code found in camera frame."}
                    )
                finally:
                    cap.release()

        # 10. generate_test_pattern
        elif action_name == "generate_test_pattern":
            if not cv2 or np is None:
                return PluginResult(success=False, error="OpenCV and numpy are required.")

            w = max(100, int(parameters.get("width", 640)))
            h = max(100, int(parameters.get("height", 480)))
            path = parameters.get("save_path", "data/camera/test_pattern.png").strip()

            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

            # Generate 8 SMPTE color bars
            colors = [
                (255, 255, 255),  # White
                (0, 255, 255),    # Yellow
                (255, 255, 0),    # Cyan
                (0, 255, 0),      # Green
                (255, 0, 255),    # Magenta
                (0, 0, 255),      # Red
                (255, 0, 0),      # Blue
                (0, 0, 0)         # Black
            ]
            bar_width = w // len(colors)
            img = np.zeros((h, w, 3), dtype=np.uint8)
            for i, col in enumerate(colors):
                x1 = i * bar_width
                x2 = w if i == len(colors) - 1 else (i + 1) * bar_width
                img[:, x1:x2] = col

            cv2.putText(img, "JARVIS CAMERA CALIBRATION", (20, h - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
            cv2.imwrite(path, img)

            return PluginResult(
                success=True,
                data={"path": os.path.abspath(path), "width": w, "height": h, "message": f"Test pattern generated at {path} ({w}x{h})."}
            )

        # 11. get_camera_device_info
        elif action_name == "get_camera_device_info":
            if not cv2:
                return PluginResult(success=False, error="OpenCV is required.")

            idx = int(parameters.get("device_index", 0))
            cap = cv2.VideoCapture(idx)
            if not cap.isOpened():
                return PluginResult(success=False, error=f"Camera index {idx} not accessible.")

            try:
                backend = cap.getBackendName()
                w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
                h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
                fps = cap.get(cv2.CAP_PROP_FPS)
                brightness = cap.get(cv2.CAP_PROP_BRIGHTNESS)
                contrast = cap.get(cv2.CAP_PROP_CONTRAST)

                return PluginResult(
                    success=True,
                    data={
                        "device_index": idx,
                        "backend": backend,
                        "resolution": f"{int(w)}x{int(h)}",
                        "fps": fps,
                        "brightness": brightness,
                        "contrast": contrast,
                        "message": f"Camera {idx}: Backend={backend}, Res={int(w)}x{int(h)}, FPS={fps}."
                    }
                )
            finally:
                cap.release()

        # 12. save_camera_snapshot_sequence
        elif action_name == "save_camera_snapshot_sequence":
            if not cv2:
                return PluginResult(success=False, error="OpenCV is required.")

            idx = int(parameters.get("device_index", 0))
            out_dir = parameters.get("output_dir", "data/camera/sequence").strip()
            count = max(1, min(20, int(parameters.get("frame_count", 5))))
            interval_ms = max(50, int(parameters.get("interval_ms", 200)))
            os.makedirs(out_dir, exist_ok=True)

            cap = cv2.VideoCapture(idx)
            if not cap.isOpened():
                return PluginResult(success=False, error=f"Camera index {idx} not accessible.")

            saved = []
            try:
                for i in range(count):
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        fp = os.path.join(out_dir, f"frame_{i+1:03d}.jpg")
                        cv2.imwrite(fp, frame)
                        saved.append(os.path.abspath(fp))
                    time.sleep(interval_ms / 1000.0)

                return PluginResult(
                    success=True,
                    data={"count": len(saved), "frames": saved, "message": f"Saved sequence of {len(saved)} frame(s) to {out_dir}."}
                )
            finally:
                cap.release()

        return PluginResult(success=False, error=f"Unknown action '{action_name}' in Camera plugin.")
