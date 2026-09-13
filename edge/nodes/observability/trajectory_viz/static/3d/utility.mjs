// Display-only transforms and age calculations. Missing headings never become north.
export const finite = value => typeof value === 'number' && Number.isFinite(value);
export function validPose(pose) {
  return !!pose && finite(pose.x) && finite(pose.y) && finite(pose.theta);
}
export function enuPosition(pose) {
  return [pose.x, finite(pose.z) ? pose.z : 0, -pose.y];
}
export function ageSeconds(sample, elapsed = 0) {
  return sample && finite(sample.age_s) ? Math.max(0, sample.age_s + elapsed) : null;
}
export function effectiveStatus(frame, elapsed = 0, failed = false) {
  if (failed) return 'offline';
  if (!frame) return 'waiting';
  if (frame.status === 'waiting') return 'waiting';
  const pose = frame.primary_source === 'truth' ? frame.truth : frame.estimate;
  if (!validPose(pose)) return 'waiting';
  const limit = finite(frame.stale_after_s) ? frame.stale_after_s : 1;
  const age = ageSeconds(pose, elapsed);
  return frame.status === 'stale' || pose.stale || age === null || age > limit ? 'stale' : 'live';
}
export function pointXY(point) {
  if (Array.isArray(point) && finite(point[0]) && finite(point[1])) return [point[0], point[1]];
  if (point && finite(point.x) && finite(point.y)) return [point.x, point.y];
  return null;
}
export function replayIndex(frames, timestamp) {
  let lo = 0, hi = frames.length - 1;
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2);
    if (frames[mid].timestamp <= timestamp) lo = mid; else hi = mid - 1;
  }
  return lo;
}
