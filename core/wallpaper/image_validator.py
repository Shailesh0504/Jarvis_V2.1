# core/wallpaper/image_validator.py
"""
Pillow-based image validation, structural integrity verification, and aspect ratio checks.
"""

import logging
import os
from typing import Optional, Tuple
from PIL import Image, UnidentifiedImageError

logger = logging.getLogger("jarvis.wallpaper.validator")

SUPPORTED_FORMATS = {"JPEG", "PNG", "WEBP", "BMP"}
MIN_DESKTOP_WIDTH = 1024
MIN_DESKTOP_HEIGHT = 600
MIN_FILE_SIZE_BYTES = 4 * 1024        # 4 KB minimum (reject tracking pixels/empty stubs)
MAX_FILE_SIZE_BYTES = 30 * 1024 * 1024  # 30 MB maximum (safety cap)


class ImageValidator:
    """Validates downloaded image files before applying as Windows wallpaper."""

    @classmethod
    def validate_file(
        cls,
        file_path: str,
        min_width: int = MIN_DESKTOP_WIDTH,
        min_height: int = MIN_DESKTOP_HEIGHT,
        require_landscape: bool = True,
    ) -> Tuple[bool, str, Optional[dict]]:
        """
        Validates file integrity, format, dimensions, and orientation.
        Returns: (is_valid, reason, metadata_dict)
        """
        if not os.path.isfile(file_path):
            return False, "File does not exist", None

        # 1. Size Validation
        file_size = os.path.getsize(file_path)
        if file_size < MIN_FILE_SIZE_BYTES:
            return False, f"File too small ({file_size} bytes), likely a placeholder or thumbnail", None
        if file_size > MAX_FILE_SIZE_BYTES:
            return False, f"File exceeds maximum safety size limit ({file_size} bytes)", None

        # 2. Magic Byte / Content Check (Reject HTML or scripts saved as .jpg)
        try:
            with open(file_path, "rb") as f:
                header = f.read(512)
                lower_header = header.lower()
                if b"<!doctype" in lower_header or b"<html" in lower_header or b"<?xml" in lower_header:
                    return False, "Downloaded content is HTML/XML text rather than binary image data", None
        except Exception as e:
            return False, f"Failed to read file header: {e}", None

        # 3. Pillow Image Structural Verification
        try:
            with Image.open(file_path) as img:
                img_format = img.format
                if not img_format or img_format.upper() not in SUPPORTED_FORMATS:
                    return False, f"Unsupported image format: {img_format}", None

                width, height = img.size
                if width < min_width or height < min_height:
                    return False, f"Resolution too low ({width}x{height}), minimum required is {min_width}x{min_height}", None

                aspect_ratio = float(width) / float(height) if height > 0 else 1.0

                if require_landscape and (width < height or aspect_ratio < 1.20):
                    return False, f"Image is in portrait orientation or non-widescreen ({width}x{height}, aspect {aspect_ratio:.2f}), desktop requires landscape", None

                metadata = {
                    "width": width,
                    "height": height,
                    "format": img_format,
                    "aspect_ratio": aspect_ratio,
                    "file_size": file_size,
                }
                return True, "Valid desktop wallpaper image", metadata
        except UnidentifiedImageError:
            return False, "File is not a recognized image or is severely corrupted", None
        except Exception as e:
            return False, f"Image validation error: {e}", None
