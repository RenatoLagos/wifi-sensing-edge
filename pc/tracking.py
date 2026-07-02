from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Sequence
from urllib import request

import numpy as np

logger = logging.getLogger(__name__)

_MODEL_DOWNLOAD_TIMEOUT_S = 30.0
_DOWNLOAD_CHUNK_BYTES = 64 * 1024

_MODEL_SPECS = {
    0: (
        "pose_landmarker_lite.task",
        "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
        "pose_landmarker_lite/float16/1/pose_landmarker_lite.task",
    ),
    1: (
        "pose_landmarker_full.task",
        "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
        "pose_landmarker_full/float16/1/pose_landmarker_full.task",
    ),
    2: (
        "pose_landmarker_heavy.task",
        "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
        "pose_landmarker_heavy/float16/1/pose_landmarker_heavy.task",
    ),
}


def _download_model(url: str, target: Path, *, timeout_s: float) -> None:
    """Download `url` to `target` atomically.

    Streams to a `<name>.part` file in the same directory and renames it
    into place only after the full body has been read, so an interrupted
    download never leaves a file a later run would mistake for a cached
    model. Any failure (connect timeout, HTTP error, partial read, empty
    body) removes the partial file and raises a RuntimeError naming the
    URL and destination.
    """
    temp_path = target.with_name(target.name + ".part")
    logger.info(
        "downloading pose model %s from %s to %s", target.name, url, target
    )
    try:
        with request.urlopen(url, timeout=timeout_s) as response:
            bytes_written = 0
            with temp_path.open("wb") as sink:
                while True:
                    chunk = response.read(_DOWNLOAD_CHUNK_BYTES)
                    if not chunk:
                        break
                    sink.write(chunk)
                    bytes_written += len(chunk)
            if bytes_written == 0:
                raise ValueError("server returned an empty body")
        temp_path.replace(target)
    except Exception as exc:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            logger.warning("could not remove partial download %s", temp_path)
        raise RuntimeError(
            f"could not download pose model from {url} to {target}: {exc}"
        ) from exc
    logger.info(
        "pose model %s downloaded (%d bytes)", target.name, target.stat().st_size
    )


def _ensure_pose_model(
    *,
    model_complexity: int,
    model_path: str | None,
    download_timeout_s: float = _MODEL_DOWNLOAD_TIMEOUT_S,
    models_dir: Path | None = None,
) -> Path:
    if model_path is not None:
        resolved = Path(model_path).expanduser().resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"pose model file does not exist: {resolved}")
        return resolved

    if model_complexity not in _MODEL_SPECS:
        raise ValueError(
            f"model_complexity must be one of {sorted(_MODEL_SPECS)}, got {model_complexity}"
        )

    filename, url = _MODEL_SPECS[model_complexity]
    directory = models_dir or Path(__file__).resolve().parents[1] / "models"
    target = directory / filename
    # A zero-byte file is a leftover from an interrupted download made by
    # older versions of this module; treat it as missing and re-download.
    if target.exists() and target.stat().st_size > 0:
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    _download_model(url, target, timeout_s=download_timeout_s)
    return target


@dataclass(frozen=True)
class PoseTrack:
    detected: bool
    confidence: float
    bbox_xyxy: tuple[int, int, int, int] | None
    segmentation_mask: np.ndarray | None
    landmarks: tuple[tuple[int, int, float], ...]


class PoseTracker:
    def __init__(
        self,
        *,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
        model_complexity: int = 0,
        model_path: str | None = None,
        download_timeout_s: float = _MODEL_DOWNLOAD_TIMEOUT_S,
    ) -> None:
        try:
            import cv2
            from mediapipe import Image, ImageFormat
            from mediapipe.tasks.python.core.base_options import BaseOptions
            from mediapipe.tasks.python.vision import (
                PoseLandmarker,
                PoseLandmarkerOptions,
                RunningMode,
            )
            from mediapipe.tasks.python.vision.pose_landmarker import (
                PoseLandmarksConnections,
            )
        except ImportError as exc:
            raise RuntimeError(
                "Install `pc/requirements.txt` to run the camera-assisted visualizer."
            ) from exc

        self._cv2 = cv2
        self._mp_image = Image
        self._mp_image_format = ImageFormat
        resolved_model = _ensure_pose_model(
            model_complexity=model_complexity,
            model_path=model_path,
            download_timeout_s=download_timeout_s,
        )
        options = PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(resolved_model)),
            running_mode=RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=min_detection_confidence,
            min_pose_presence_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
            output_segmentation_masks=True,
        )
        self._pose = PoseLandmarker.create_from_options(options)
        self.connections: Sequence[tuple[int, int]] = tuple(
            (connection.start, connection.end)
            for connection in PoseLandmarksConnections.POSE_LANDMARKS
        )

    def close(self) -> None:
        self._pose.close()

    def process(self, frame_bgr: np.ndarray, *, timestamp_ms: int) -> PoseTrack:
        frame_rgb = self._cv2.cvtColor(frame_bgr, self._cv2.COLOR_BGR2RGB)
        mp_image = self._mp_image(
            image_format=self._mp_image_format.SRGB,
            data=frame_rgb,
        )
        result = self._pose.detect_for_video(mp_image, timestamp_ms)
        if not result.pose_landmarks:
            return PoseTrack(
                detected=False,
                confidence=0.0,
                bbox_xyxy=None,
                segmentation_mask=None,
                landmarks=(),
            )

        height, width = frame_bgr.shape[:2]
        landmarks: list[tuple[int, int, float]] = []
        visible_points: list[tuple[int, int]] = []
        visibilities: list[float] = []
        for landmark in result.pose_landmarks[0]:
            x = int(np.clip(landmark.x, 0.0, 1.0) * (width - 1))
            y = int(np.clip(landmark.y, 0.0, 1.0) * (height - 1))
            visibility = float(landmark.visibility)
            landmarks.append((x, y, visibility))
            if visibility >= 0.5:
                visible_points.append((x, y))
                visibilities.append(visibility)

        if not visible_points:
            return PoseTrack(
                detected=False,
                confidence=0.0,
                bbox_xyxy=None,
                segmentation_mask=None,
                landmarks=tuple(landmarks),
            )

        xs = [p[0] for p in visible_points]
        ys = [p[1] for p in visible_points]
        x0 = max(0, min(xs) - 24)
        y0 = max(0, min(ys) - 24)
        x1 = min(width - 1, max(xs) + 24)
        y1 = min(height - 1, max(ys) + 24)

        mask = None
        if result.segmentation_masks:
            mask = np.clip(
                result.segmentation_masks[0].numpy_view().astype(np.float32),
                0.0,
                1.0,
            )

        return PoseTrack(
            detected=True,
            confidence=float(np.mean(visibilities)),
            bbox_xyxy=(x0, y0, x1, y1),
            segmentation_mask=mask,
            landmarks=tuple(landmarks),
        )
