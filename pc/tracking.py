from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np


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
    ) -> None:
        try:
            import cv2
            import mediapipe as mp
        except ImportError as exc:
            raise RuntimeError(
                "Install `pc/requirements.txt` to run the camera-assisted visualizer."
            ) from exc

        self._cv2 = cv2
        self._mp = mp
        self._pose = mp.solutions.pose.Pose(
            static_image_mode=False,
            model_complexity=model_complexity,
            enable_segmentation=True,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )
        self.connections: Sequence[tuple[int, int]] = tuple(
            mp.solutions.pose.POSE_CONNECTIONS
        )

    def close(self) -> None:
        self._pose.close()

    def process(self, frame_bgr: np.ndarray) -> PoseTrack:
        frame_rgb = self._cv2.cvtColor(frame_bgr, self._cv2.COLOR_BGR2RGB)
        result = self._pose.process(frame_rgb)
        if result.pose_landmarks is None:
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
        for landmark in result.pose_landmarks.landmark:
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
        if (
            hasattr(result, "segmentation_mask")
            and result.segmentation_mask is not None
        ):
            mask = np.clip(result.segmentation_mask.astype(np.float32), 0.0, 1.0)

        return PoseTrack(
            detected=True,
            confidence=float(np.mean(visibilities)),
            bbox_xyxy=(x0, y0, x1, y1),
            segmentation_mask=mask,
            landmarks=tuple(landmarks),
        )
