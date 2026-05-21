from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
from urllib import request

import numpy as np


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


def _ensure_pose_model(*, model_complexity: int, model_path: str | None) -> Path:
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
    target = Path(__file__).resolve().parents[1] / "models" / filename
    if target.exists():
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        request.urlretrieve(url, target)
    except Exception as exc:  # pragma: no cover - network-dependent path
        raise RuntimeError(
            f"could not download pose model from {url} to {target}"
        ) from exc
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
