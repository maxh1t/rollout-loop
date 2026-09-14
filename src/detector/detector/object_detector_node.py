import resource
import time

import cv2
import numpy as np
import onnxruntime as ort
import rclpy
from ament_index_python.packages import get_package_share_directory
from cv_bridge import CvBridge
from rclpy.node import Node
from sensor_msgs.msg import Image
from vision_msgs.msg import (
    BoundingBox2D,
    Detection2D,
    Detection2DArray,
    ObjectHypothesis,
    ObjectHypothesisWithPose,
)

from detector.coco_classes import COCO_CLASSES

# How often (in processed frames) to log the running FPS/latency/memory
# numbers this ticket needs. Every frame would be noisy; a periodic summary
# is enough to characterize sustained-load performance.
LOG_INTERVAL_FRAMES = 30

# Padding color used by YOLO's own letterbox preprocessing (mid-gray).
LETTERBOX_COLOR = (114, 114, 114)


class ObjectDetectorNode(Node):
    """Runs a YOLOv8n ONNX model (CPU, via ONNX Runtime) on frames from
    /camera/image_raw and publishes the results on /detector/objects
    (vision_msgs/Detection2DArray), plus an annotated copy of the frame with
    boxes drawn on it on /detector/objects/annotated for viewing in
    Foxglove.

    This is separate from the frame-differencing motion detector_node — that
    one keeps running unchanged; this is the new P2 on-device object
    detector.
    """

    def __init__(self):
        super().__init__('object_detector_node')

        self.declare_parameter('resolution', 640)
        self.declare_parameter('conf_threshold', 0.5)
        self.declare_parameter('iou_threshold', 0.45)
        self.declare_parameter('classes', ['person'])

        self.resolution = \
            self.get_parameter('resolution').get_parameter_value().integer_value
        self.conf_threshold = \
            self.get_parameter('conf_threshold').get_parameter_value().double_value
        self.iou_threshold = \
            self.get_parameter('iou_threshold').get_parameter_value().double_value
        target_classes = \
            self.get_parameter('classes').get_parameter_value().string_array_value
        self.target_class_ids = {
            COCO_CLASSES.index(name) for name in target_classes if name in COCO_CLASSES
        }
        unknown = [name for name in target_classes if name not in COCO_CLASSES]
        if unknown:
            self.get_logger().warning(f'Ignoring unknown class name(s): {unknown}')

        model_path = (
            f'{get_package_share_directory("detector")}/models/'
            f'yolov8n_{self.resolution}.onnx'
        )
        self.session = ort.InferenceSession(
            model_path, providers=['CPUExecutionProvider'])
        self.input_name = self.session.get_inputs()[0].name

        self.bridge = CvBridge()
        self.subscription = self.create_subscription(
            Image, '/camera/image_raw', self.on_image, 10)
        self.detections_pub = self.create_publisher(
            Detection2DArray, '/detector/objects', 10)
        self.annotated_pub = self.create_publisher(
            Image, '/detector/objects/annotated', 10)

        self.frame_count = 0
        self.inference_time_total = 0.0
        self.window_start = time.monotonic()

        classes_desc = sorted(target_classes) if self.target_class_ids else ['all']
        self.get_logger().info(
            f'Running YOLOv8n ONNX ({self.resolution}x{self.resolution}) on CPU, '
            f'classes={classes_desc}, conf_threshold={self.conf_threshold}, '
            f'iou_threshold={self.iou_threshold}')

    def on_image(self, msg):
        frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')

        blob, scale, pad = self._letterbox(frame, self.resolution)

        t0 = time.monotonic()
        output = self.session.run(None, {self.input_name: blob})[0]
        inference_s = time.monotonic() - t0

        detections = self._postprocess(output, frame.shape, scale, pad)

        self._publish_detections(detections, msg.header)
        self._publish_annotated(frame, detections, msg.header)
        self._log_stats(inference_s)

    @staticmethod
    def _letterbox(frame, size):
        """Resize+pad frame to a size x size square, preserving aspect
        ratio, matching the preprocessing YOLO was trained/exported with.
        Returns the NCHW float32 blob plus the scale and padding needed to
        map box coordinates back to the original frame.
        """
        h, w = frame.shape[:2]
        scale = min(size / h, size / w)
        new_w, new_h = round(w * scale), round(h * scale)
        resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

        pad_w, pad_h = size - new_w, size - new_h
        top, bottom = pad_h // 2, pad_h - pad_h // 2
        left, right = pad_w // 2, pad_w - pad_w // 2
        padded = cv2.copyMakeBorder(
            resized, top, bottom, left, right,
            cv2.BORDER_CONSTANT, value=LETTERBOX_COLOR)

        rgb = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        blob = np.transpose(rgb, (2, 0, 1))[np.newaxis, ...]
        return blob, scale, (left, top)

    def _postprocess(self, output, frame_shape, scale, pad):
        """output: (1, 84, N) -> list of (x1, y1, x2, y2, class_id, score)
        in original-frame pixel coordinates, filtered to target classes and
        NMS'd.
        """
        h, w = frame_shape[:2]
        pad_x, pad_y = pad

        rows = output[0].T  # (N, 84)
        class_scores = rows[:, 4:]
        class_ids = np.argmax(class_scores, axis=1)
        scores = class_scores[np.arange(len(rows)), class_ids]

        keep = scores >= self.conf_threshold
        if self.target_class_ids:
            keep &= np.isin(class_ids, list(self.target_class_ids))
        rows, class_ids, scores = rows[keep], class_ids[keep], scores[keep]
        if len(rows) == 0:
            return []

        cx, cy, bw, bh = rows[:, 0], rows[:, 1], rows[:, 2], rows[:, 3]
        x1, y1 = cx - bw / 2, cy - bh / 2
        nms_boxes = np.stack([x1, y1, bw, bh], axis=1).tolist()

        indices = cv2.dnn.NMSBoxes(
            nms_boxes, scores.tolist(), self.conf_threshold, self.iou_threshold)
        if len(indices) == 0:
            return []
        indices = np.array(indices).flatten()

        detections = []
        for i in indices:
            # Undo letterbox padding/scale to map back to the original frame.
            ox1 = np.clip((x1[i] - pad_x) / scale, 0, w)
            oy1 = np.clip((y1[i] - pad_y) / scale, 0, h)
            ox2 = np.clip((x1[i] + bw[i] - pad_x) / scale, 0, w)
            oy2 = np.clip((y1[i] + bh[i] - pad_y) / scale, 0, h)
            detections.append((ox1, oy1, ox2, oy2, int(class_ids[i]), float(scores[i])))
        return detections

    def _publish_detections(self, detections, header):
        msg = Detection2DArray()
        msg.header = header
        for x1, y1, x2, y2, class_id, score in detections:
            det = Detection2D()
            det.header = header
            det.bbox = BoundingBox2D()
            det.bbox.center.position.x = (x1 + x2) / 2
            det.bbox.center.position.y = (y1 + y2) / 2
            det.bbox.size_x = x2 - x1
            det.bbox.size_y = y2 - y1
            hyp = ObjectHypothesisWithPose()
            hyp.hypothesis = ObjectHypothesis()
            hyp.hypothesis.class_id = COCO_CLASSES[class_id]
            hyp.hypothesis.score = score
            det.results = [hyp]
            msg.detections.append(det)
        self.detections_pub.publish(msg)

    def _publish_annotated(self, frame, detections, header):
        annotated = frame.copy()
        for x1, y1, x2, y2, class_id, score in detections:
            p1, p2 = (int(x1), int(y1)), (int(x2), int(y2))
            cv2.rectangle(annotated, p1, p2, (0, 255, 0), 2)
            label = f'{COCO_CLASSES[class_id]} {score:.2f}'
            cv2.putText(annotated, label, (p1[0], max(p1[1] - 8, 0)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        out = self.bridge.cv2_to_imgmsg(annotated, encoding='bgr8')
        out.header = header
        self.annotated_pub.publish(out)

    def _log_stats(self, inference_s):
        self.frame_count += 1
        self.inference_time_total += inference_s
        if self.frame_count % LOG_INTERVAL_FRAMES == 0:
            elapsed = time.monotonic() - self.window_start
            fps = LOG_INTERVAL_FRAMES / elapsed if elapsed > 0 else 0.0
            avg_latency_ms = (self.inference_time_total / LOG_INTERVAL_FRAMES) * 1000
            rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
            self.get_logger().info(
                f'fps={fps:.1f} avg_inference_latency_ms={avg_latency_ms:.1f} '
                f'peak_rss_mb={rss_mb:.1f}')
            self.window_start = time.monotonic()
            self.inference_time_total = 0.0


def main():
    rclpy.init()
    node = ObjectDetectorNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
