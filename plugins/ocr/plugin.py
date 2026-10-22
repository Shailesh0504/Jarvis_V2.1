# plugins/ocr/plugin.py
"""OCR capability plugin implementation for extracting text from images, screen, and bounding regions."""

import logging
import os
import shutil
from typing import Any, Dict, List, Optional
from PIL import Image, ImageFilter, ImageGrab, ImageOps

from plugins.base import BasePlugin
from plugins.manifest import PluginManifest, PluginResult
from .commands import ACTIONS
from .permissions import PERMISSIONS_REQUIRED

logger = logging.getLogger("jarvis.plugins.ocr")


class OcrPlugin(BasePlugin):
    """Controls image, screen, and document optical character recognition."""

    def __init__(self, manifest: Optional[PluginManifest] = None, config: Optional[Dict[str, Any]] = None):
        super().__init__(manifest=manifest, config=config)
        self._tesseract_cmd = self._find_tesseract_binary()
        self._setup_pytesseract()

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="ocr",
            version="2.0.0",
            description="Optical Character Recognition (OCR) text extractor from images, screen, and regions.",
            author="Jarvis Team",
            permissions=PERMISSIONS_REQUIRED,
            actions=ACTIONS
        )

    def _find_tesseract_binary(self) -> Optional[str]:
        candidates = [
            shutil.which("tesseract"),
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe")
        ]
        for c in candidates:
            if c and os.path.isfile(c):
                return os.path.abspath(c)
        return None

    def _setup_pytesseract(self) -> bool:
        try:
            import pytesseract
            if self._tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = self._tesseract_cmd
            return True
        except ImportError:
            return False

    def check_dependencies(self) -> bool:
        has_lib = self._setup_pytesseract()
        has_bin = self._tesseract_cmd is not None
        return has_lib and has_bin

    def verify_state(self, action_name: str, parameters: Dict[str, Any], result_data: Any) -> Optional[Any]:
        from core.execution.models import VerificationResult, ExecutionState
        if action_name in ("save_ocr_result_to_file", "preprocess_image_for_ocr"):
            out_path = parameters.get("output_path")
            if out_path and os.path.isfile(out_path) and os.path.getsize(out_path) > 0:
                return VerificationResult(
                    verified=True,
                    state=ExecutionState.SUCCESS,
                    check_type="file_exists",
                    expected=out_path,
                    actual=f"{os.path.getsize(out_path)} bytes",
                    message="OCR output file verified on disk."
                )
            return VerificationResult(
                verified=False,
                state=ExecutionState.FAILED,
                check_type="file_exists",
                expected=out_path,
                actual=None,
                error="Expected OCR output file not created."
            )
        return None

    def _preprocess(self, img: Image.Image) -> Image.Image:
        """Enhances image contrast and sharpens text boundaries for OCR accuracy."""
        gray = ImageOps.grayscale(img)
        enhanced = gray.filter(ImageFilter.SHARPEN)
        return enhanced

    def execute(self, action_name: str, parameters: Optional[Dict[str, Any]] = None) -> PluginResult:
        parameters = parameters or {}

        # 1. check_ocr_engine_available
        if action_name == "check_ocr_engine_available":
            has_pytesseract = self._setup_pytesseract()
            has_binary = self._tesseract_cmd is not None
            is_ready = has_pytesseract and has_binary
            return PluginResult(
                success=True,
                data={
                    "ready": is_ready,
                    "pytesseract_installed": has_pytesseract,
                    "tesseract_binary": self._tesseract_cmd,
                    "message": "OCR engine is ready and operational." if is_ready else "Tesseract binary not found; image dimensions and preprocessing remain available."
                }
            )

        # 2. get_image_dimensions
        elif action_name == "get_image_dimensions":
            img_path = parameters.get("image_path", "").strip()
            if not img_path or not os.path.isfile(img_path):
                return PluginResult(success=False, error=f"Image file not found: '{img_path}'")

            try:
                with Image.open(img_path) as img:
                    w, h = img.size
                    fmt = img.format
                    mode = img.mode
                mp = round((w * h) / 1_000_000.0, 2)
                return PluginResult(
                    success=True,
                    data={
                        "path": img_path,
                        "width": w,
                        "height": h,
                        "format": fmt,
                        "mode": mode,
                        "megapixels": mp,
                        "message": f"Image '{os.path.basename(img_path)}' resolution: {w}x{h} ({mp} MP, {fmt})."
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Failed to inspect image: {e}")

        # 3. preprocess_image_for_ocr
        elif action_name == "preprocess_image_for_ocr":
            img_path = parameters.get("image_path", "").strip()
            out_path = parameters.get("output_path", "").strip()
            if not img_path or not os.path.isfile(img_path):
                return PluginResult(success=False, error=f"Image file not found: '{img_path}'")
            if not out_path:
                return PluginResult(success=False, error="output_path is required.")

            try:
                with Image.open(img_path) as img:
                    enhanced = self._preprocess(img)
                    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
                    enhanced.save(out_path)

                return PluginResult(
                    success=True,
                    data={"input_path": img_path, "output_path": out_path, "message": f"Enhanced preprocessed image saved to '{out_path}'."}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Preprocessing failed: {e}")

        # 4. extract_text_from_image
        elif action_name == "extract_text_from_image":
            img_path = parameters.get("image_path", "").strip()
            do_preprocess = bool(parameters.get("preprocess", True))
            if not img_path or not os.path.isfile(img_path):
                return PluginResult(success=False, error=f"Image file not found: '{img_path}'")

            if not self._tesseract_cmd:
                return PluginResult(
                    success=False,
                    error="Tesseract OCR binary not found. Please install Tesseract-OCR to enable image text extraction."
                )

            try:
                import pytesseract
                with Image.open(img_path) as img:
                    target = self._preprocess(img) if do_preprocess else img
                    text = pytesseract.image_to_string(target).strip()

                preview = text[:300] + ("..." if len(text) > 300 else "")
                return PluginResult(
                    success=True,
                    data={"text": text, "preview": preview, "char_count": len(text), "message": f"Extracted text: {preview or '[No text detected]'}"}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"OCR extraction failed: {e}")

        # 5. extract_text_from_screen
        elif action_name == "extract_text_from_screen":
            if not self._tesseract_cmd:
                return PluginResult(
                    success=False,
                    error="Tesseract OCR binary not found. Please install Tesseract-OCR for screen text recognition."
                )

            try:
                import pytesseract
                screenshot = ImageGrab.grab()
                enhanced = self._preprocess(screenshot)
                text = pytesseract.image_to_string(enhanced).strip()
                preview = text[:300] + ("..." if len(text) > 300 else "")
                return PluginResult(
                    success=True,
                    data={"text": text, "preview": preview, "message": f"Screen text: '{preview or '[No text detected]'}'"}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Screen OCR failed: {e}")

        # 6. extract_text_from_screen_region
        elif action_name == "extract_text_from_screen_region":
            if not self._tesseract_cmd:
                return PluginResult(success=False, error="Tesseract OCR binary not found.")

            try:
                x = int(parameters.get("x", 0))
                y = int(parameters.get("y", 0))
                w = int(parameters.get("width", 100))
                h = int(parameters.get("height", 100))
                bbox = (x, y, x + w, y + h)

                import pytesseract
                screenshot = ImageGrab.grab(bbox=bbox)
                enhanced = self._preprocess(screenshot)
                text = pytesseract.image_to_string(enhanced).strip()

                return PluginResult(
                    success=True,
                    data={"region": {"x": x, "y": y, "width": w, "height": h}, "text": text, "message": f"Region OCR extracted: '{text[:200]}'"}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Region OCR failed: {e}")

        # 7. find_word_on_screen
        elif action_name == "find_word_on_screen":
            word = parameters.get("word", "").strip().lower()
            if not word:
                return PluginResult(success=False, error="word to search is required.")
            if not self._tesseract_cmd:
                return PluginResult(success=False, error="Tesseract OCR binary not found.")

            try:
                import pytesseract
                screenshot = ImageGrab.grab()
                data = pytesseract.image_to_data(screenshot, output_type=pytesseract.Output.DICT)
                matches = []
                n_boxes = len(data["text"])
                for i in range(n_boxes):
                    text_box = (data["text"][i] or "").strip().lower()
                    if word in text_box and int(data["conf"][i]) > 30:
                        matches.append({
                            "word": data["text"][i],
                            "x": data["left"][i],
                            "y": data["top"][i],
                            "width": data["width"][i],
                            "height": data["height"][i],
                            "confidence": data["conf"][i]
                        })

                return PluginResult(
                    success=True,
                    data={"matches_count": len(matches), "matches": matches, "message": f"Found '{word}' at {len(matches)} screen position(s)."}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Find word failed: {e}")

        # 8. extract_digits_only
        elif action_name == "extract_digits_only":
            img_path = parameters.get("image_path", "").strip()
            if not img_path or not os.path.isfile(img_path):
                return PluginResult(success=False, error=f"Image file not found: '{img_path}'")
            if not self._tesseract_cmd:
                return PluginResult(success=False, error="Tesseract OCR binary not found.")

            try:
                import pytesseract
                with Image.open(img_path) as img:
                    enhanced = self._preprocess(img)
                    text = pytesseract.image_to_string(enhanced, config="--psm 6 outputbase digits")
                digits = "".join(c for c in text if c.isdigit() or c in ("\n", " ", ".", "-")).strip()
                return PluginResult(
                    success=True,
                    data={"digits": digits, "message": f"Extracted digits: '{digits}'"}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Digit extraction failed: {e}")

        # 9. extract_and_copy_to_clipboard
        elif action_name == "extract_and_copy_to_clipboard":
            img_path = parameters.get("image_path", "").strip()
            res = self.execute("extract_text_from_image" if img_path else "extract_text_from_screen", parameters)
            if not res.success:
                return res

            text = res.data.get("text", "")
            try:
                import ctypes
                user32 = ctypes.windll.user32
                kernel32 = ctypes.windll.kernel32
                if user32.OpenClipboard(None):
                    user32.EmptyClipboard()
                    data = text.encode("utf-16-le") + b"\x00\x00"
                    h_glob = kernel32.GlobalAlloc(2, len(data))
                    p_glob = kernel32.GlobalLock(h_glob)
                    ctypes.memmove(p_glob, data, len(data))
                    kernel32.GlobalUnlock(h_glob)
                    user32.SetClipboardData(13, h_glob)
                    user32.CloseClipboard()
                return PluginResult(success=True, data={"text": text, "message": f"OCR text ({len(text)} chars) copied to clipboard."})
            except Exception as e:
                return PluginResult(success=True, data={"text": text, "clipboard_error": str(e), "message": "Extracted text but clipboard write failed."})

        # 10. save_ocr_result_to_file
        elif action_name == "save_ocr_result_to_file":
            img_path = parameters.get("image_path", "").strip()
            out_path = parameters.get("output_path", "").strip()
            if not out_path:
                return PluginResult(success=False, error="output_path is required.")

            res = self.execute("extract_text_from_image", {"image_path": img_path})
            if not res.success:
                return res

            try:
                os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(res.data.get("text", ""))

                return PluginResult(
                    success=True,
                    data={"output_path": out_path, "size_bytes": os.path.getsize(out_path), "message": f"Saved OCR text to '{out_path}'."}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Failed saving OCR text: {e}")

        # 11. batch_ocr_images
        elif action_name == "batch_ocr_images":
            dir_path = parameters.get("directory_path", "").strip()
            out_file = parameters.get("output_file", "").strip()
            if not dir_path or not os.path.isdir(dir_path):
                return PluginResult(success=False, error=f"Directory not found: '{dir_path}'")

            valid_exts = (".png", ".jpg", ".jpeg", ".bmp", ".tiff")
            image_files = [os.path.join(dir_path, f) for f in sorted(os.listdir(dir_path)) if f.lower().endswith(valid_exts)]

            if not image_files:
                return PluginResult(success=True, data={"files_processed": 0, "results": [], "message": f"No image files found in '{dir_path}'."})

            results = []
            compiled_text = []
            for img_f in image_files:
                sub_res = self.execute("extract_text_from_image", {"image_path": img_f})
                if sub_res.success:
                    txt = sub_res.data.get("text", "")
                    results.append({"file": os.path.basename(img_f), "text": txt, "chars": len(txt)})
                    compiled_text.append(f"=== {os.path.basename(img_f)} ===\n{txt}")

            if out_file and compiled_text:
                try:
                    os.makedirs(os.path.dirname(os.path.abspath(out_file)), exist_ok=True)
                    with open(out_file, "w", encoding="utf-8") as f:
                        f.write("\n\n".join(compiled_text))
                except Exception as e:
                    logger.error("Failed writing batch OCR output: %s", e)

            return PluginResult(
                success=True,
                data={"files_processed": len(results), "results": results, "output_file": out_file or None, "message": f"Processed {len(results)} images."}
            )

        # 12. get_ocr_confidence_score
        elif action_name == "get_ocr_confidence_score":
            img_path = parameters.get("image_path", "").strip()
            if not img_path or not os.path.isfile(img_path):
                return PluginResult(success=False, error=f"Image file not found: '{img_path}'")
            if not self._tesseract_cmd:
                return PluginResult(success=False, error="Tesseract OCR binary not found.")

            try:
                import pytesseract
                with Image.open(img_path) as img:
                    data = pytesseract.image_to_data(self._preprocess(img), output_type=pytesseract.Output.DICT)
                confs = [int(c) for c in data["conf"] if int(c) >= 0]
                avg_conf = round(sum(confs) / len(confs), 2) if confs else 0.0
                return PluginResult(
                    success=True,
                    data={"average_confidence": avg_conf, "words_detected": len(confs), "message": f"OCR confidence: {avg_conf}% across {len(confs)} words."}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Confidence calculation failed: {e}")

        return PluginResult(success=False, error=f"Unknown action '{action_name}' in OCR plugin.")
