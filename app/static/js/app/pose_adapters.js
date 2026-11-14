// Map MediaPipe's 33 pose landmarks to the 17 canonical COCO keypoints the server expects.
// Output: { name: [x, y, confidence] } in normalised image coordinates (y grows downwards).

const MEDIAPIPE_TO_COCO = {
  nose: 0, l_eye: 2, r_eye: 5, l_ear: 7, r_ear: 8, l_shoulder: 11, r_shoulder: 12, l_elbow: 13, r_elbow: 14,
  l_wrist: 15, r_wrist: 16, l_hip: 23, r_hip: 24, l_knee: 25, r_knee: 26, l_ankle: 27, r_ankle: 28,
};

export const SKELETON = [
  ['l_shoulder', 'r_shoulder'], ['l_shoulder', 'l_elbow'], ['l_elbow', 'l_wrist'], ['r_shoulder', 'r_elbow'],
  ['r_elbow', 'r_wrist'], ['l_shoulder', 'l_hip'], ['r_shoulder', 'r_hip'], ['l_hip', 'r_hip'],
  ['l_hip', 'l_knee'], ['l_knee', 'l_ankle'], ['r_hip', 'r_knee'], ['r_knee', 'r_ankle'], ['nose', 'l_eye'],
  ['nose', 'r_eye'],
];

export function mediapipeToCoco(landmarks) {
  if (!landmarks || landmarks.length < 33) return null;
  const out = {};
  for (const [name, index] of Object.entries(MEDIAPIPE_TO_COCO)) {
    const point = landmarks[index];
    const confidence = point.visibility ?? point.presence ?? 0;
    out[name] = [Number(point.x.toFixed(4)), Number(point.y.toFixed(4)), Number(confidence.toFixed(3))];
  }
  return out;
}

export function meanConfidence(keypoints) {
  const values = Object.values(keypoints || {}).map((point) => point[2]);
  return values.length ? values.reduce((a, b) => a + b, 0) / values.length : 0;
}
