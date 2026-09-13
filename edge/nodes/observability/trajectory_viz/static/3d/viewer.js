import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { finite, validPose, enuPosition, ageSeconds, effectiveStatus, pointXY, replayIndex } from './utility.mjs';

const $ = id => document.getElementById(id);
const ui = Object.fromEntries(['connection-status', 'status-dot', 'empty-state', 'error-message',
  'source-badge', 'task-name', 'position-source', 'pose-age', 'speed-value', 'algorithm-value',
  'implement-value', 'coverage-value', 'coverage-note', 'frame-time', 'model-status',
  'replay-controls', 'play-replay', 'replay-range', 'replay-time', 'worked-label', 'untreated-label'].map(id => [id, $(id)]));
const state = {
  mode: 'live', frame: null, receivedAt: 0, failed: false, sceneFailed: false,
  taskId: undefined, liveTaskId: undefined, sceneRevision: -1, sceneData: null, view: 'oblique',
  frames: [], replayGround: null, replayTrace: null, replayClock: 0, replayPosition: 0, playing: false, replayLoad: 0,
  fitDone: false, poseFitDone: false, modelReady: false, reducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches,
};
const container = $('canvas-container');
let renderer;
try {
  renderer = new THREE.WebGLRenderer({antialias: true, alpha: false});
} catch (error) {
  ui['error-message'].textContent = '此浏览器无法启动三维显示，请启用图形加速或打开二维轨迹。';
  ui['error-message'].hidden = false;
  throw error;
}
renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
renderer.setClearColor(0xeaf0e8);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.3;
container.appendChild(renderer.domElement);
const scene = new THREE.Scene();
scene.fog = new THREE.Fog(0xeaf0e8, 180, 600);
const camera = new THREE.PerspectiveCamera(42, 1, 0.05, 3000);
camera.position.set(16, 21, 24);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.09;
controls.minDistance = 2;
controls.maxDistance = 1200;
controls.maxPolarAngle = Math.PI / 2 - 0.025;
controls.target.set(0, 0, 0);
scene.add(new THREE.HemisphereLight(0xffffff, 0x617953, 2.7));
const sun = new THREE.DirectionalLight(0xfff3da, 3.4);
sun.position.set(35, 55, 20);
scene.add(sun);
const ground = new THREE.Mesh(new THREE.PlaneGeometry(2000, 2000), new THREE.MeshStandardMaterial({color: 0xe0e8d9, roughness: 1}));
ground.rotation.x = -Math.PI / 2;
ground.position.y = -0.055;
scene.add(ground);
const grid = new THREE.GridHelper(200, 100, 0xc1cebc, 0xd1dbcb);
grid.position.y = -0.04;
grid.material.transparent = true;
grid.material.opacity = 0.45;
scene.add(grid);
const layers = {};
for (const name of ['field', 'plan', 'actual', 'coverage', 'analysis', 'replay', 'replayGround']) {
  layers[name] = new THREE.Group(); scene.add(layers[name]);
}
const target = new THREE.Mesh(new THREE.TorusGeometry(0.22, 0.035, 8, 36), new THREE.MeshBasicMaterial({color: 0x8065b2}));
target.rotation.x = -Math.PI / 2; target.visible = false; scene.add(target);
const vehicles = {};
let modelTemplate = null;
const up = new THREE.Vector3(0, 1, 0), forward = new THREE.Vector3(1, 0, 0), right = new THREE.Vector3(0, 0, 1);
const tempQuaternion = new THREE.Quaternion();

// Meter-scaled soil textures are generated locally once. Their fine grain is
// decorative; footprint geometry alone determines which ground was worked.
function soilTexture(worked) {
  const size = 512, canvas = document.createElement('canvas');
  canvas.width = size; canvas.height = size;
  const ctx = canvas.getContext('2d');
  const pixels = ctx.createImageData(size, size);
  let seed = worked ? 29031 : 17849;
  const random = () => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed / 4294967296; };
  const base = worked ? [94, 62, 39] : [180, 157, 111];
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const grain = (random() - 0.5) * (worked ? 24 : 34);
      const mottle = Math.sin(x * Math.PI * 8 / size) * Math.cos(y * Math.PI * 6 / size) * 5;
      const ridge = worked ? Math.sin((y / size * 25 + Math.sin(x * Math.PI * 4 / size) * 0.04) * Math.PI * 2) * 10 : 0;
      const offset = (y * size + x) * 4;
      for (let channel = 0; channel < 3; channel++) pixels.data[offset + channel] = base[channel] + grain + mottle + ridge;
      pixels.data[offset + 3] = 255;
    }
  }
  ctx.putImageData(pixels, 0, 0);
  if (!worked) {
    // A sparse scatter of dry stubble makes untouched soil readable close up.
    ctx.lineWidth = 1.2;
    for (let i = 0; i < 950; i++) {
      const x = random() * size, y = random() * size, angle = random() * Math.PI;
      const length = 2 + random() * 4;
      ctx.strokeStyle = random() < 0.5 ? '#c6b482' : '#8f805a';
      ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + Math.cos(angle) * length, y + Math.sin(angle) * length); ctx.stroke();
    }
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(0.5, 0.5); // One 2 × 2 m tile, coherent across polygons.
  texture.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
  return texture;
}
const soilTextures = {untreated: soilTexture(false), worked: soilTexture(true)};
function soilMaterial(worked) {
  return new THREE.MeshStandardMaterial({map: soilTextures[worked ? 'worked' : 'untreated'], roughness: 1, side: THREE.DoubleSide});
}


function disposeGroup(group) {
  const geometries = new Set(), materials = new Set();
  group.traverse(object => {
    if (object.geometry) geometries.add(object.geometry);
    if (object.material) for (const material of Array.isArray(object.material) ? object.material : [object.material]) materials.add(material);
  });
  group.clear();
  geometries.forEach(geometry => geometry.dispose());
  materials.forEach(material => material.dispose());
}

function line(points, color, altitude = 0.06, closed = false) {
  const valid = (points || []).map(pointXY).filter(Boolean);
  if (valid.length < 2) return null;
  const vertices = valid.map(([x, y]) => new THREE.Vector3(x, altitude, -y));
  if (closed) vertices.push(vertices[0].clone());
  return new THREE.Line(new THREE.BufferGeometry().setFromPoints(vertices), new THREE.LineBasicMaterial({color}));
}

function polygonShape(exterior, holes = []) {
  const ring = (exterior || []).map(pointXY).filter(Boolean);
  if (ring.length < 3) return null;
  const shape = new THREE.Shape(ring.map(([x, y]) => new THREE.Vector2(x, y)));
  for (const hole of holes || []) {
    const valid = hole.map(pointXY).filter(Boolean);
    if (valid.length >= 3) shape.holes.push(new THREE.Path(valid.map(([x, y]) => new THREE.Vector2(x, y))));
  }
  return shape;
}

function addPolygon(group, polygon, color, altitude, opacity = 1) {
  const shape = polygonShape(Array.isArray(polygon) ? polygon : polygon?.exterior, polygon?.holes);
  if (!shape) return;
  const geometry = new THREE.ShapeGeometry(shape);
  geometry.rotateX(-Math.PI / 2);
  const material = new THREE.MeshStandardMaterial({color, roughness: 1, side: THREE.DoubleSide, transparent: opacity < 1, opacity, depthWrite: opacity === 1});
  const mesh = new THREE.Mesh(geometry, material);
  mesh.position.y = altitude;
  group.add(mesh);
}

function addSoil(group, polygon, worked, altitude) {
  const shape = polygonShape(Array.isArray(polygon) ? polygon : polygon?.exterior, polygon?.holes);
  if (!shape) return;
  const geometry = new THREE.ShapeGeometry(shape);
  // ShapeGeometry's UVs are the original ground coordinates (meters), before
  // rotating from ENU into the viewer's Y-up scene.
  geometry.rotateX(-Math.PI / 2);
  const mesh = new THREE.Mesh(geometry, soilMaterial(worked));
  mesh.position.y = altitude;
  group.add(mesh);
}

function clearReplayLayers() {
  disposeGroup(layers.replay); disposeGroup(layers.replayGround);
  state.replayGround = null; state.replayTrace = null;
}

function setTask(taskId) {
  if (taskId === state.taskId) return false;
  state.taskId = taskId;
  state.sceneData = null;
  state.sceneRevision = -1;
  state.frames = [];
  state.replayGround = null; state.replayTrace = null;
  state.replayLoad += 1;
  state.playing = false;
  state.fitDone = false;
  state.poseFitDone = false;
  state.frame = null;
  for (const layer of Object.values(layers)) disposeGroup(layer);
  for (const vehicle of Object.values(vehicles)) { vehicle.group.visible = false; vehicle.initialized = false; }
  target.visible = false;
  ui['task-name'].textContent = taskId == null || taskId === '' ? '未指定任务' : `任务 ${taskId}`;
  ui['coverage-value'].textContent = '—';
  ui['replay-time'].textContent = '暂无记录';
  $('replay-range').disabled = true;
  $('play-replay').disabled = true;
  if (state.mode === 'replay') enterLive();
  return true;
}

function drawScene(data) {
  state.sceneData = data;
  for (const name of ['field', 'plan', 'actual', 'coverage', 'analysis']) disposeGroup(layers[name]);
  const boundary = data.field_boundary || [];
  const holes = data.field_holes || [];
  addSoil(layers.field, {exterior: boundary, holes}, false, -0.018);
  const edge = line(boundary, 0x6e7d56, 0.025, true);
  if (edge) layers.field.add(edge);
  for (const hole of holes) {
    const outline = line(hole, 0x6e7d56, 0.025, true); if (outline) layers.field.add(outline);
  }
  const planned = line(data.planned_path, 0xb68242, 0.045);
  if (planned) layers.plan.add(planned);
  const actual = line(data.actual_trajectory, 0x287657, 0.065);
  if (actual) layers.actual.add(actual);
  const overlay = data.coverage_overlay || {};
  for (const polygon of overlay.covered ?? overlay.polygons ?? []) addSoil(layers.coverage, polygon, true, 0.0);
  const categories = [
    [overlay.covered ?? overlay.polygons, 0x86ae67, 0.01],
    [overlay.repeated, 0xd6a343, 0.014],
    [overlay.missed, 0xdf8d76, 0.006],
  ];
  for (const [polygons, color, altitude] of categories) {
    for (const polygon of polygons || []) addPolygon(layers.analysis, polygon, color, altitude, 0.74);
  }
  if (!state.fitDone && (boundary.length || (data.planned_path || []).length)) {
    fitScene(); state.fitDone = true;
  }
  updateLayerVisibility();
  renderStatus();
}

function fitScene(view = state.view) {
  const points = [
    ...(state.sceneData?.field_boundary || []), ...(state.sceneData?.planned_path || []),
    ...(state.sceneData?.actual_trajectory || []),
  ].map(pointXY).filter(Boolean);
  const current = state.frame?.[state.frame.primary_source];
  if (validPose(current)) points.push([current.x, current.y]);
  if (!points.length) points.push([-6, -6], [6, 6]);
  const box = new THREE.Box3();
  points.forEach(([x, y]) => box.expandByPoint(new THREE.Vector3(x, 0, -y)));
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const span = Math.max(size.x / camera.aspect, size.z, 8);
  const distance = span / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2))) * 1.35;
  controls.target.copy(center);
  if (view === 'top') camera.position.copy(center).add(new THREE.Vector3(0, distance, 0.001));
  else camera.position.copy(center).add(new THREE.Vector3(distance * 0.35, distance * 0.8, distance * 0.65));
  camera.lookAt(center);
  ground.position.x = center.x; ground.position.z = center.z;
  grid.position.x = Math.round(center.x / 2) * 2; grid.position.z = Math.round(center.z / 2) * 2;
  scene.fog.near = Math.max(180, distance * 3); scene.fog.far = Math.max(600, distance * 7);
  camera.far = Math.max(3000, distance * 10); camera.updateProjectionMatrix();
  controls.update();
}

function setView(view) {
  state.view = view;
  document.querySelectorAll('[data-view]').forEach(button => button.classList.toggle('active', button.dataset.view === view));
  if (view === 'follow') {
    const pose = state.frame?.[state.frame.primary_source];
    if (validPose(pose)) {
      controls.target.fromArray(enuPosition(pose));
      camera.position.copy(controls.target).add(new THREE.Vector3(7, 7, 9));
      controls.update();
    }
  } else fitScene(view);
}

function makeVehicle(name) {
  const group = new THREE.Group();
  const body = modelTemplate.clone(true);
  const materials = [];
  body.traverse(object => {
    if (object.isMesh) {
      object.material = Array.isArray(object.material) ? object.material.map(material => material.clone()) : object.material.clone();
      for (const material of Array.isArray(object.material) ? object.material : [object.material]) {
        material.userData.originalColor = material.color?.clone();
        materials.push(material);
      }
    }
  });
  group.add(body); group.visible = false; scene.add(group);
  const hitch = body.getObjectByName('implement_lift');
  hitch?.traverse(object => {
    for (const material of object.material ? (Array.isArray(object.material) ? object.material : [object.material]) : []) material.userData.implementPart = true;
  });
  vehicles[name] = {group, body, materials, hitch, hitchBase: hitch?.position.y ?? 0, initialized: false,
    from: new THREE.Vector3(), to: new THREE.Vector3(), fromQ: new THREE.Quaternion(), toQ: new THREE.Quaternion(), updated: 0};
}

function poseQuaternion(pose) {
  const q = new THREE.Quaternion().setFromAxisAngle(up, pose.theta);
  if (finite(pose.pitch)) q.multiply(tempQuaternion.setFromAxisAngle(right, -pose.pitch));
  if (finite(pose.roll)) q.multiply(tempQuaternion.setFromAxisAngle(forward, pose.roll));
  return q;
}

function applyFrame(frame, snap = false) {
  const now = performance.now();
  state.frame = frame;
  state.receivedAt = now;
  for (const name of ['truth', 'estimate']) {
    const vehicle = vehicles[name]; if (!vehicle) continue;
    const pose = frame?.[name];
    if (!validPose(pose)) { vehicle.group.visible = false; vehicle.initialized = false; continue; }
    const isGhost = name === 'estimate' && frame.mode === 'simulation';
    vehicle.group.visible = !isGhost || $('show-estimate').checked;
    for (const material of vehicle.materials) {
      material.transparent = isGhost;
      material.opacity = isGhost ? 0.3 : 1;
      material.depthWrite = !isGhost;
      if (material.color) material.color.copy(isGhost ? new THREE.Color(0x429cc4) : material.userData.originalColor);
    }
    vehicle.from.copy(vehicle.group.position); vehicle.fromQ.copy(vehicle.group.quaternion);
    vehicle.to.fromArray(enuPosition(pose)); vehicle.toQ.copy(poseQuaternion(pose));
    vehicle.updated = now;
    if (snap || !vehicle.initialized || pose.stale || state.reducedMotion) {
      vehicle.group.position.copy(vehicle.to); vehicle.group.quaternion.copy(vehicle.toQ);
      vehicle.from.copy(vehicle.to); vehicle.fromQ.copy(vehicle.toQ);
    }
    vehicle.initialized = true;
    const implement = frame.implement;
    const measuredImplement = implement && ['simulation_truth', 'feedback'].includes(implement.source)
      && !implement.stale && finite(implement.hitch_height);
    if (vehicle.hitch && measuredImplement) {
      vehicle.hitch.position.y = vehicle.hitchBase + (1 - THREE.MathUtils.clamp(implement.hitch_height, 0, 1)) * 0.25;
    }
    if (!measuredImplement) {
      for (const material of vehicle.materials.filter(material => material.userData.implementPart)) {
        material.color?.setHex(0x91988d); material.transparent = true; material.opacity = 0.35; material.depthWrite = false;
      }
    }
  }
  const next = frame?.target;
  target.visible = !!next && finite(next.x) && finite(next.y) && finite(next.age_s) && next.age_s <= (frame.stale_after_s ?? 1);
  if (target.visible) target.position.set(next.x, 0.12, -next.y);
  ui['empty-state'].hidden = validPose(frame?.truth) || validPose(frame?.estimate);
  if (!state.fitDone && !state.poseFitDone && validPose(frame?.[frame.primary_source])) {
    fitScene();
    // Allow a later field/path packet to choose the full-task framing once.
    state.poseFitDone = true;
  }
  renderStatus();
}

function updateLayerVisibility() {
  const groundVisible = $('show-coverage').checked;
  const analysisVisible = state.mode === 'live' && $('show-analysis').checked;
  layers.coverage.visible = state.mode === 'live' && groundVisible;
  layers.replayGround.visible = state.mode === 'replay' && groundVisible && !!state.replayGround?.available;
  layers.analysis.visible = analysisVisible;
  document.querySelectorAll('.analysis-legend').forEach(label => { label.hidden = !analysisVisible; });
  document.querySelectorAll('.soil-legend').forEach(label => { label.hidden = !groundVisible || analysisVisible; });
  layers.actual.visible = state.mode === 'live';
  layers.replay.visible = state.mode === 'replay';
  const estimate = vehicles.estimate;
  if (estimate) estimate.group.visible = validPose(state.frame?.estimate) && (state.frame.mode !== 'simulation' || $('show-estimate').checked);
}

function sourceLabel(frame) {
  if (!frame) return '—';
  if (!validPose(frame[frame.primary_source])) return frame.mode === 'simulation' ? '真值未到' : '等待有效定位';
  return frame.primary_source === 'truth' ? '仿真真值' : '定位估计';
}
function shortAge(age) { return age === null ? '未知' : `${age.toFixed(age < 10 ? 2 : 0)} 秒`; }
function clockText(timestamp) { return finite(timestamp) ? new Date(timestamp * 1000).toLocaleTimeString('zh-CN', {hour12: false}) : '时间未知'; }
function renderStatus() {
  const frame = state.frame;
  const elapsed = state.mode === 'live' ? (performance.now() - state.receivedAt) / 1000 : 0;
  const status = effectiveStatus(frame, elapsed, state.failed);
  const labels = {waiting: '等待数据', live: '在线', stale: '数据过期', offline: '连接中断'};
  ui['connection-status'].textContent = state.mode === 'replay' ? (state.playing ? '正在回放' : '回放已暂停') : labels[status];
  ui['status-dot'].className = `status-dot ${state.mode === 'replay' ? 'waiting' : status}`;
  ui['position-source'].textContent = sourceLabel(frame);
  ui['source-badge'].textContent = !frame ? '等待位置来源' : frame.mode === 'simulation' ? '仿真观察' : '实车监控';
  const pose = frame?.[frame.primary_source];
  ui['pose-age'].textContent = validPose(pose) ? shortAge(ageSeconds(pose, elapsed)) : '—';
  const targetAge = ageSeconds(frame?.target, elapsed);
  if (targetAge === null || targetAge > (frame?.stale_after_s ?? 1)) target.visible = false;
  const command = frame?.command;
  const commandAge = ageSeconds(command, elapsed);
  const commandStale = commandAge === null || commandAge > (frame?.stale_after_s ?? 1);
  ui['speed-value'].textContent = finite(command?.linear_velocity) ? `${command.linear_velocity.toFixed(2)} m/s${commandStale ? ' · 过期' : ''}` : '—';
  const algorithms = {heading_p: '前瞻点比例', pure_pursuit: '纯跟踪'};
  ui['algorithm-value'].textContent = command?.tracking_method ? (algorithms[command.tracking_method] || command.tracking_method) : '—';
  const implement = frame?.implement;
  const implementAge = ageSeconds(implement, elapsed);
  if (!implement || implement.source === 'unknown' || !finite(implement.hitch_height)) ui['implement-value'].textContent = '未知';
  else {
    const height = implement.hitch_height >= 0.95 ? '落下' : implement.hitch_height <= 0.05 ? '抬起' : '升降中';
    const pto = typeof implement.pto_on === 'boolean' ? implement.pto_on ? '运转' : '停转' : '转动未知';
    const stale = implement.stale || implementAge === null || implementAge > (frame?.stale_after_s ?? 1);
    const source = implement.source === 'controller_status' ? '控制器状态 · 未接实测' : `${height} / ${pto}`;
    ui['implement-value'].textContent = `${source}${stale ? ' · 过期' : ''}`;
  }
  const overlay = state.sceneData?.coverage_overlay;
  const rate = overlay?.coverage_rate_percent;
  ui['coverage-value'].textContent = state.mode === 'replay' ? '—' : finite(rate) ? `${rate.toFixed(1)}%` : '—';
  const coverageSource = overlay?.position_source === 'simulation_truth' ? '仿真真值' : ['estimated_pose', 'estimate'].includes(overlay?.position_source) ? '定位估计' : '等待数据';
  const implementSources = {simulation_truth: '机具仿真真值', feedback: '机具实测反馈', controller_status: '机具按控制状态估算', command_estimate: '机具按指令估算'};
  const implementSource = implementSources[overlay?.implement_source] || '机具状态未知';
  const coverageExtra = overlay?.display_geometry_truncated ? ' · 显示已简化' : '';
  if (state.mode === 'replay') {
    const ground = state.replayGround;
    ui['worked-label'].textContent = '本段已处理';
    ui['untreated-label'].textContent = ground?.available ? '本段未处理' : '地面状态未知';
    ui['coverage-note'].textContent = ground?.available
      ? `仅显示本段记录内扫掠${ground.estimated ? ' · 按估计状态绘制' : ''}`
      : '本段没有可用的地面处理记录';
  } else {
    ui['worked-label'].textContent = '已处理'; ui['untreated-label'].textContent = '未处理';
    ui['coverage-note'].textContent = `覆盖依据：${coverageSource} · ${implementSource}${coverageExtra}${state.sceneFailed ? ' · 场景更新中断' : ''}`;
  }
  if (state.modelReady) {
    const width = overlay?.implement_width_m;
    ui['model-status'].textContent = `模型示意 1.6 × 1.2 米${finite(width) ? ` · 配置作业幅宽 ${width.toFixed(1)} 米` : ''}`;
  }
  ui['frame-time'].textContent = frame ? `${state.mode === 'replay' ? '记录' : '最近帧'} ${clockText(frame.timestamp)}` : '等待首帧';
}

async function fetchJSON(url, timeoutMs = 2500) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {cache: 'no-store', signal: controller.signal});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } finally { clearTimeout(timeout); }
}

async function pollFrame() {
  try {
    const frame = await fetchJSON('/api/monitor/frame');
    state.failed = false;
    // Live frames remain authoritative while the visible frame is a replay.
    state.liveTaskId = frame ? (frame.task_id ?? null) : undefined;
    if (frame && frame.task_id !== state.taskId) setTask(frame.task_id);
    if (state.mode === 'live') applyFrame(frame);
  } catch (_) { state.failed = true; renderStatus(); }
  finally { setTimeout(pollFrame, 100); }
}

async function pollScene() {
  try {
    const previousTask = state.taskId;
    const result = await fetchJSON(`/api/monitor/scene?since=${encodeURIComponent(state.sceneRevision)}`);
    state.sceneFailed = false;
    // Scene computation can lag behind frames even when the request started
    // after a task switch. Never let such a response roll task B back to A.
    if (result.data && state.liveTaskId !== undefined && (result.data.task_id ?? null) !== state.liveTaskId) return;
    // A frame can announce another task while this response is in flight.
    if (previousTask !== state.taskId && result.data && result.data.task_id !== state.taskId) return;
    if (!result.unchanged && result.data) {
      setTask(result.data.task_id);
      state.sceneRevision = result.revision;
      drawScene(result.data);
    }
  } catch (_) { state.sceneFailed = true; }
  finally { setTimeout(pollScene, 1000); }
}

function enterLive() {
  state.mode = 'live'; state.playing = false; state.replayLoad += 1;
  $('live-mode').classList.add('active'); $('replay-mode').classList.remove('active');
  ui['replay-controls'].hidden = true; $('show-analysis').disabled = false;
  state.frames = []; clearReplayLayers();
  updateLayerVisibility();
  // No extrapolation from the last replay pose while awaiting a live frame.
  state.frame = null;
  for (const vehicle of Object.values(vehicles)) { vehicle.initialized = false; vehicle.group.visible = false; }
  target.visible = false;
  renderStatus();
}

function buildReplayLayers(entries, ground) {
  clearReplayLayers();
  const traceVertices = [], traceCounts = [];
  for (const frame of state.frames) {
    const pose = frame?.[frame.primary_source];
    if (validPose(pose)) traceVertices.push(pose.x, 0.07, -pose.y);
    traceCounts.push(traceVertices.length / 3);
  }
  const traceGeometry = new THREE.BufferGeometry();
  traceGeometry.setAttribute('position', new THREE.Float32BufferAttribute(traceVertices, 3));
  traceGeometry.setDrawRange(0, 0);
  layers.replay.add(new THREE.Line(traceGeometry, new THREE.LineBasicMaterial({color: 0x287657})));
  state.replayTrace = {geometry: traceGeometry, counts: traceCounts};
  state.replayGround = {...ground, available: ground?.available === true, counts: []};
  if (!state.replayGround.available) return;

  // Map the API's original frame indexes after validating and ordering frames.
  // Geometry is built once; scrubbing only changes a vertex prefix draw range.
  const byFrame = new Map(entries.map((entry, index) => [entry.originalIndex, index]));
  const segments = (ground.segments || []).filter(segment => byFrame.has(segment.frame_index))
    .sort((a, b) => byFrame.get(a.frame_index) - byFrame.get(b.frame_index));
  const vertices = [], uvs = [], counts = Array(state.frames.length).fill(0);
  for (const segment of segments) {
    for (const polygon of segment.polygons || []) {
      const shape = polygonShape(Array.isArray(polygon) ? polygon : polygon?.exterior, polygon?.holes);
      if (!shape) continue;
      const indexed = new THREE.ShapeGeometry(shape);
      const geometry = indexed.toNonIndexed();
      const position = geometry.getAttribute('position'), uv = geometry.getAttribute('uv');
      for (let i = 0; i < position.count; i++) {
        vertices.push(position.getX(i), 0, -position.getY(i));
        uvs.push(uv.getX(i), uv.getY(i));
      }
      counts[byFrame.get(segment.frame_index)] += position.count;
      geometry.dispose(); indexed.dispose();
    }
  }
  for (let index = 1; index < counts.length; index++) counts[index] += counts[index - 1];
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
  geometry.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
  geometry.computeVertexNormals(); geometry.setDrawRange(0, 0);
  layers.replayGround.add(new THREE.Mesh(geometry, soilMaterial(true)));
  state.replayGround.geometry = geometry; state.replayGround.counts = counts;
}

function updateReplayLayers() {
  const index = state.replayPosition;
  const trace = state.replayTrace, ground = state.replayGround;
  trace?.geometry.setDrawRange(0, trace.counts[index] || 0);
  ground?.geometry?.setDrawRange(0, ground.counts[index] || 0);
}

function showReplayFrame(index, snap = false) {
  state.replayPosition = Math.max(0, Math.min(state.frames.length - 1, index));
  const frame = state.frames[state.replayPosition];
  if (!frame) return;
  applyFrame(frame, snap);
  $('replay-range').value = String(state.replayPosition);
  ui['replay-time'].textContent = `${clockText(frame.timestamp)} / ${clockText(state.frames.at(-1).timestamp)}`;
  updateReplayLayers();
}

async function enterReplay() {
  state.mode = 'replay'; state.playing = false;
  const request = ++state.replayLoad;
  const task = state.taskId;
  $('live-mode').classList.remove('active'); $('replay-mode').classList.add('active');
  ui['replay-controls'].hidden = false; $('show-analysis').disabled = true;
  $('play-replay').disabled = true; $('replay-range').disabled = true;
  ui['replay-time'].textContent = '正在读取';
  ui['play-replay'].textContent = '播放';
  state.frames = []; clearReplayLayers(); applyFrame(null, true);
  updateLayerVisibility(); renderStatus();
  try {
    const result = await fetchJSON('/api/monitor/replay?ground=1', 15000);
    if (state.mode !== 'replay' || request !== state.replayLoad || task !== state.taskId) return;
    const entries = (result.frames || []).map((frame, originalIndex) => ({frame, originalIndex}))
      .filter(({frame}) => frame && finite(frame.timestamp) && frame.task_id === task)
      .slice(-6000).sort((a, b) => a.frame.timestamp - b.frame.timestamp);
    state.frames = entries.map(entry => entry.frame);
    buildReplayLayers(entries, result.ground);
    updateLayerVisibility(); renderStatus();
    if (!state.frames.length) { ui['replay-time'].textContent = '暂无记录'; return; }
    $('play-replay').disabled = false; $('replay-range').disabled = false;
    $('replay-range').max = String(state.frames.length - 1);
    state.replayClock = state.frames[0].timestamp;
    showReplayFrame(0, true);
  } catch (_) {
    if (request === state.replayLoad) ui['replay-time'].textContent = '读取失败';
  }
}

for (const button of document.querySelectorAll('[data-view]')) button.addEventListener('click', () => setView(button.dataset.view));
$('fit-view').addEventListener('click', () => { if (state.view === 'follow') setView('oblique'); else fitScene(); });
$('show-estimate').addEventListener('change', updateLayerVisibility);
$('show-coverage').addEventListener('change', updateLayerVisibility);
$('show-analysis').addEventListener('change', updateLayerVisibility);
$('live-mode').addEventListener('click', enterLive);
$('replay-mode').addEventListener('click', enterReplay);
$('play-replay').addEventListener('click', () => {
  if (!state.frames.length) return;
  if (state.replayPosition === state.frames.length - 1) { state.replayClock = state.frames[0].timestamp; showReplayFrame(0, true); }
  state.playing = !state.playing;
  ui['play-replay'].textContent = state.playing ? '暂停' : '播放'; renderStatus();
});
$('replay-range').addEventListener('input', () => {
  state.playing = false; ui['play-replay'].textContent = '播放';
  const index = Number($('replay-range').value);
  state.replayClock = state.frames[index]?.timestamp ?? 0;
  showReplayFrame(index, true);
});
controls.addEventListener('start', () => {
  if (state.view === 'follow') {
    state.view = 'free'; document.querySelectorAll('[data-view]').forEach(button => button.classList.remove('active'));
  }
});
new ResizeObserver(() => {
  const {width, height} = container.getBoundingClientRect();
  if (!width || !height) return;
  renderer.setSize(width, height); camera.aspect = width / height; camera.updateProjectionMatrix();
}).observe(container);

new GLTFLoader().load('/assets/tracked_tiller.glb', gltf => {
  modelTemplate = gltf.scene;
  makeVehicle('truth'); makeVehicle('estimate');
  state.modelReady = true;
  ui['model-status'].textContent = '模型示意 1.6 × 1.2 米';
  if (state.frame) applyFrame(state.frame, true);
}, undefined, () => {
  ui['model-status'].textContent = '车辆模型未能载入';
  ui['error-message'].textContent = '车辆模型加载失败；路线和覆盖仍可查看。';
  ui['error-message'].hidden = false;
});

let previousTime = performance.now();
function animate(now) {
  const dt = Math.min((now - previousTime) / 1000, 0.1); previousTime = now;
  if (state.mode === 'replay' && state.playing && state.frames.length) {
    state.replayClock += dt * Number($('replay-speed').value);
    const index = replayIndex(state.frames, state.replayClock);
    if (index !== state.replayPosition) showReplayFrame(index);
    if (state.replayClock >= state.frames.at(-1).timestamp) { state.playing = false; ui['play-replay'].textContent = '播放'; }
  }
  const live = state.mode === 'replay' || effectiveStatus(state.frame, (now - state.receivedAt) / 1000, state.failed) === 'live';
  if (live) {
    for (const vehicle of Object.values(vehicles)) {
      if (!vehicle.initialized || !vehicle.group.visible) continue;
      const alpha = Math.min(1, (now - vehicle.updated) / 110);
      vehicle.group.position.lerpVectors(vehicle.from, vehicle.to, alpha);
      vehicle.group.quaternion.slerpQuaternions(vehicle.fromQ, vehicle.toQ, alpha);
    }
  }
  if (state.view === 'follow') {
    const vehicle = vehicles[state.frame?.primary_source];
    if (vehicle?.group.visible) {
      const delta = vehicle.group.position.clone().sub(controls.target).multiplyScalar(1 - Math.exp(-dt * 6));
      controls.target.add(delta); camera.position.add(delta);
    }
  }
  controls.update(); renderer.render(scene, camera); requestAnimationFrame(animate);
}
requestAnimationFrame(animate);
setInterval(renderStatus, 150);
pollFrame(); pollScene();
