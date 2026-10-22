# plugins/camera/commands.py
"""Command actions supported by Camera Plugin."""

from plugins.manifest import PluginAction, PluginParameter
from core.permissions import PermissionLevel, PluginCapability

ACTIONS = [
    # Existing Actions
    PluginAction(
        name="capture_photo",
        description="Captures a photo using the system webcam/camera",
        keywords=["capture photo", "take picture", "photo kheencho", "camera snap", "webcam photo"],
        parameters=[
            PluginParameter(name="save_path", type="string", description="Optional save path for the image", required=False, default=""),
            PluginParameter(name="device_index", type="integer", description="Webcam device index (0 for default)", required=False, default=0)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.CAMERA.value
    ),
    PluginAction(
        name="open_camera_app",
        description="Opens the Windows Camera application",
        keywords=["open camera", "camera kholo", "webcam open karo"],
        parameters=[],
        required_permission=PermissionLevel.EXECUTE,
        required_capability=PluginCapability.CAMERA.value
    ),

    # 10 New Actions
    PluginAction(
        name="record_video_clip",
        description="Records a short video clip from the webcam to an MP4 or AVI file",
        keywords=["record video", "video record karo", "capture video clip", "webcam video"],
        parameters=[
            PluginParameter(name="save_path", type="string", description="Output video file path (.avi or .mp4)", required=False, default=""),
            PluginParameter(name="duration_seconds", type="integer", description="Recording duration in seconds", required=False, default=5),
            PluginParameter(name="device_index", type="integer", description="Camera device index", required=False, default=0)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.CAMERA.value
    ),
    PluginAction(
        name="capture_burst_photos",
        description="Captures multiple rapid burst photos in sequence from the camera",
        keywords=["burst photos", "multiple photos", "rapid photos", "burst snap"],
        parameters=[
            PluginParameter(name="output_dir", type="string", description="Directory to store captured burst photos", required=False, default="data/camera"),
            PluginParameter(name="count", type="integer", description="Number of photos to capture", required=False, default=3),
            PluginParameter(name="interval_seconds", type="number", description="Delay between shots", required=False, default=0.5),
            PluginParameter(name="device_index", type="integer", description="Camera index", required=False, default=0)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.CAMERA.value
    ),
    PluginAction(
        name="list_camera_devices",
        description="Scans and lists all detected hardware webcam devices and their availability",
        keywords=["list cameras", "detect webcams", "webcam devices", "camera list"],
        parameters=[
            PluginParameter(name="max_devices_to_probe", type="integer", description="Max device indices to probe", required=False, default=4)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.CAMERA.value
    ),
    PluginAction(
        name="get_camera_resolution",
        description="Queries the native width, height, and FPS supported by a camera device",
        keywords=["camera resolution", "webcam width height", "camera fps", "camera specs"],
        parameters=[
            PluginParameter(name="device_index", type="integer", description="Camera device index", required=False, default=0)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.CAMERA.value
    ),
    PluginAction(
        name="capture_motion_snapshot",
        description="Compares consecutive camera frames and triggers a capture if movement is detected",
        keywords=["motion detect", "motion snapshot", "detect movement camera", "harqat detect karo"],
        parameters=[
            PluginParameter(name="save_path", type="string", description="Target save path if motion detected", required=False, default=""),
            PluginParameter(name="threshold", type="integer", description="Sensitivity delta threshold (10-100)", required=False, default=25),
            PluginParameter(name="device_index", type="integer", description="Camera index", required=False, default=0)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.CAMERA.value
    ),
    PluginAction(
        name="apply_camera_filter",
        description="Applies image processing filters (grayscale, blur, edge, sepia, invert) to an image",
        keywords=["filter photo", "photo filter lagao", "grayscale photo", "edge detect"],
        parameters=[
            PluginParameter(name="image_path", type="string", description="Input image file path", required=True),
            PluginParameter(name="filter_type", type="string", description="Filter: grayscale, blur, edges, sepia, invert", required=False, default="grayscale"),
            PluginParameter(name="save_path", type="string", description="Filtered image destination path", required=False, default="")
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="detect_qr_code",
        description="Scans an image or live webcam frame for QR codes and decodes their text data",
        keywords=["read qr code", "scan qr", "qr code decode karo", "qr reader"],
        parameters=[
            PluginParameter(name="image_path", type="string", description="Optional image file path (scans camera if empty)", required=False, default=""),
            PluginParameter(name="device_index", type="integer", description="Camera device index if scanning live", required=False, default=0)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.CAMERA.value
    ),
    PluginAction(
        name="generate_test_pattern",
        description="Generates a standardized color calibration test card image for camera testing",
        keywords=["test pattern", "camera test card", "color bars", "calibration image"],
        parameters=[
            PluginParameter(name="save_path", type="string", description="File path to save test pattern (.png or .jpg)", required=False, default="data/camera/test_pattern.png"),
            PluginParameter(name="width", type="integer", description="Pattern width in pixels", required=False, default=640),
            PluginParameter(name="height", type="integer", description="Pattern height in pixels", required=False, default=480)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.FILESYSTEM.value
    ),
    PluginAction(
        name="get_camera_device_info",
        description="Returns detailed hardware and driver properties of the selected camera index",
        keywords=["camera info", "webcam properties", "camera backend", "webcam details"],
        parameters=[
            PluginParameter(name="device_index", type="integer", description="Camera device index", required=False, default=0)
        ],
        required_permission=PermissionLevel.READ,
        required_capability=PluginCapability.CAMERA.value
    ),
    PluginAction(
        name="save_camera_snapshot_sequence",
        description="Captures a sequence of images at regular intervals for timelapse analysis",
        keywords=["timelapse photos", "interval capture", "photo sequence", "timelapse frames"],
        parameters=[
            PluginParameter(name="output_dir", type="string", description="Directory to save snapshot sequence", required=False, default="data/camera/sequence"),
            PluginParameter(name="frame_count", type="integer", description="Total frames to capture", required=False, default=5),
            PluginParameter(name="interval_ms", type="integer", description="Interval between shots in milliseconds", required=False, default=200),
            PluginParameter(name="device_index", type="integer", description="Camera device index", required=False, default=0)
        ],
        required_permission=PermissionLevel.WRITE,
        required_capability=PluginCapability.CAMERA.value
    )
]
