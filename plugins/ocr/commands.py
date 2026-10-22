# plugins/ocr/commands.py
"""Command actions supported by OCR Plugin."""

from plugins.manifest import PluginAction, PluginParameter
from core.permissions import PermissionLevel, PluginCapability

ACTIONS = [
    # Existing Actions
    PluginAction(
        name="extract_text_from_image",
        description="Performs Optical Character Recognition (OCR) to extract text from an image file",
        keywords=["ocr image", "image se text nikalo", "read text from photo", "extract image text"],
        parameters=[
            PluginParameter(name="image_path", type="string", description="Path to image file", required=True),
            PluginParameter(name="preprocess", type="boolean", description="Apply image pre-processing for clarity", required=False, default=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="extract_text_from_screen",
        description="Captures the screen and extracts on-screen text via OCR",
        keywords=["screen ocr", "screen se text padho", "read screen text", "screen text extract karo"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),

    # 10 New Actions
    PluginAction(
        name="check_ocr_engine_available",
        description="Checks whether Tesseract OCR binary and libraries are installed and operational",
        keywords=["check ocr", "ocr status", "is ocr working", "tesseract status"],
        parameters=[],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="extract_text_from_screen_region",
        description="Captures a specific bounding region on the display and extracts text",
        keywords=["region ocr", "crop ocr", "area se text padho", "extract region text"],
        parameters=[
            PluginParameter(name="x", type="integer", description="Top-left X coordinate", required=True),
            PluginParameter(name="y", type="integer", description="Top-left Y coordinate", required=True),
            PluginParameter(name="width", type="integer", description="Region width", required=True),
            PluginParameter(name="height", type="integer", description="Region height", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="find_word_on_screen",
        description="Searches on-screen text for a specific word and returns bounding coordinates",
        keywords=["find word on screen", "screen par word dhoondho", "locate text on screen"],
        parameters=[
            PluginParameter(name="word", type="string", description="Word or phrase to locate", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="extract_digits_only",
        description="Specialized OCR mode restricted to numeric digits, prices, codes, or telephone numbers",
        keywords=["extract numbers ocr", "digits ocr", "number padho image se", "extract digits"],
        parameters=[
            PluginParameter(name="image_path", type="string", description="Path to image file", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="extract_and_copy_to_clipboard",
        description="Performs OCR on an image or screen and immediately copies the result to system clipboard",
        keywords=["ocr to clipboard", "read and copy", "screen text copy karo", "ocr clipboard"],
        parameters=[
            PluginParameter(name="image_path", type="string", description="Optional image path, grabs screen if omitted", required=False, default="")
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.SYSTEM_CONTROL.value
    ),
    PluginAction(
        name="save_ocr_result_to_file",
        description="Extracts OCR text from an image or screen and saves it directly to a text file",
        keywords=["ocr save file", "ocr to txt", "text file mein save karo", "save ocr"],
        parameters=[
            PluginParameter(name="image_path", type="string", description="Source image path", required=True),
            PluginParameter(name="output_path", type="string", description="Destination text file path", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="preprocess_image_for_ocr",
        description="Applies grayscale, thresholding, and contrast sharpening to an image for improved OCR legibility",
        keywords=["preprocess ocr image", "clean image ocr", "sharpen for ocr", "image enhance ocr"],
        parameters=[
            PluginParameter(name="image_path", type="string", description="Source image path", required=True),
            PluginParameter(name="output_path", type="string", description="Destination enhanced image path", required=True)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="get_image_dimensions",
        description="Inspects image dimensions, color mode, format, and megapixel count without OCR",
        keywords=["image dimensions", "image size", "photo details", "image resolution"],
        parameters=[
            PluginParameter(name="image_path", type="string", description="Path to image file", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="batch_ocr_images",
        description="Runs OCR across multiple image files in a directory and compiles the results",
        keywords=["batch ocr", "multiple images ocr", "folder ocr", "saari photos se text nikalo"],
        parameters=[
            PluginParameter(name="directory_path", type="string", description="Directory containing images", required=True),
            PluginParameter(name="output_file", type="string", description="Optional output text file", required=False, default="")
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="get_ocr_confidence_score",
        description="Returns detailed OCR data including per-word confidence levels and bounding boxes",
        keywords=["ocr confidence", "ocr score", "ocr accuracy check"],
        parameters=[
            PluginParameter(name="image_path", type="string", description="Path to image file", required=True)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.FILESYSTEM.value
    )
]
