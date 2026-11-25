/* Draw recorded simulator snapshots. Sensor values come exclusively from frames. */
(() => {
  "use strict";
  const THREE = window.THREE;
  // Colours are written as sRGB hex; with sRGB output they must be converted to linear first.
  const c = hex => new THREE.Color(hex).convertSRGBToLinear();
  const cm = value => Number(value) / 100;
  const heading = degrees => Number(degrees) * Math.PI / 180;
  const point = (x, y, height = 0) => new THREE.Vector3(cm(x), height, -cm(y));
  const colors = {red: 0xd24646, green: 0x35b374, blue: 0x3c66df, brown: 0x8a5438,
    yellow: 0xefd578, white: 0xdde4ef, black: 0x242933};
  const headings = {front: 0, left: 90, back: 180, right: 270};

  function clear(group) {
    for (const child of [...group.children]) {
      child.traverse(item => {
        item.geometry?.dispose();
        if (item.material) {
          item.material.map?.dispose();
          item.material.dispose();
        }
      });
      group.remove(child);
    }
  }

  function box(width, height, depth, color, opacity = 1) {
    const mesh = new THREE.Mesh(
      new THREE.BoxGeometry(width, height, depth),
      new THREE.MeshStandardMaterial({color: c(color), opacity, transparent: opacity < 1,
        roughness: 0.78, depthWrite: opacity === 1}),
    );
    mesh.castShadow = opacity === 1;
    mesh.receiveShadow = true;
    return mesh;
  }

  function outline(mesh, color) {
    const line = new THREE.LineSegments(new THREE.EdgesGeometry(mesh.geometry),
      new THREE.LineBasicMaterial({color: c(color)}));
    mesh.add(line);
  }

  function cone(length, halfAngle, color, opacity) {
    const vertices = [0, 0, 0];
    for (let index = 0; index <= 24; index++) {
      const angle = halfAngle * (index / 12 - 1);
      vertices.push(length * Math.cos(angle), 0, -length * Math.sin(angle));
    }
    const mesh = new THREE.BufferGeometry();
    mesh.setAttribute("position", new THREE.Float32BufferAttribute(vertices, 3));
    mesh.setIndex(Array.from({length: 24}, (_, i) => [0, i + 1, i + 2]).flat());
    const fan = new THREE.Mesh(mesh, new THREE.MeshBasicMaterial({
      color: c(color), opacity, side: THREE.DoubleSide, transparent: true, depthWrite: false,
    }));
    fan.position.y = 0.24;
    return fan;
  }

  function observationLabel(text) {
    const canvas = document.createElement("canvas");
    canvas.width = 512;
    canvas.height = 80;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#172331";
    ctx.fillRect(0, 0, 512, 80);
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.font = "500 27px Segoe UI, sans-serif";
    ctx.fillStyle = "#fff";
    ctx.fillText(text, 256, 40, 478);
    const texture = new THREE.CanvasTexture(canvas);
    texture.encoding = THREE.sRGBEncoding;
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({map: texture}));
    sprite.scale.set(1.6, 0.25, 1);
    return sprite;
  }

  class WorldViewer {
    constructor(canvas, hud, fallback) {
      this.canvas = canvas;
      this.hud = hud;
      this.fallback = fallback;
      this.frame = null;
      this.mode = "orbit";
      this.azimuth = -2.5;
      this.elevation = 0.92;
      this.distance = 4.7;
      try {
        this.renderer = new THREE.WebGLRenderer({canvas, antialias: true});
      } catch {
        fallback.hidden = false;
        return;
      }
      this.renderer.setClearColor(0x0e1522);
      // Render at 1.5x or more even on a 1x screen, then let the browser scale down: smooths edges.
      this.renderer.setPixelRatio(Math.min(Math.max(devicePixelRatio, 1.5), 2));
      this.renderer.outputEncoding = THREE.sRGBEncoding;
      this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
      this.renderer.toneMappingExposure = 1.0;
      this.renderer.shadowMap.enabled = true;
      this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
      this.scene = new THREE.Scene();
      this.scene.background = new THREE.Color(0x0e1522); // the clear colour is not sRGB-encoded in r128
      this.scene.fog = new THREE.Fog(c(0x0e1522), 7, 22);
      this.camera = new THREE.PerspectiveCamera(46, 1, 0.03, 120);
      this.light = new THREE.HemisphereLight(c(0xdfe9ff), c(0x2a3446), 0.8);
      this.scene.add(this.light);
      this.key = new THREE.DirectionalLight(0xffffff, 1.25);
      this.key.position.set(2, 5, 3);
      this.key.castShadow = true;
      this.key.shadow.mapSize.set(2048, 2048);
      this.key.shadow.bias = -0.0004;
      this.key.shadow.radius = 3;
      this.scene.add(this.key, this.key.target);
      const fill = new THREE.DirectionalLight(c(0x8fb4ff), 0.3);
      fill.position.set(-3, 2, -2);
      this.scene.add(fill);
      this.world = new THREE.Group();
      this.robot = new THREE.Group();
      this.cast = new THREE.Group();
      this.scene.add(this.world, this.robot, this.cast);
      const body = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.21, 0.14, 56),
        new THREE.MeshStandardMaterial({color: c(0x2fbf9f), roughness: 0.42, metalness: 0.25}));
      body.position.y = 0.11;
      const deck = new THREE.Mesh(new THREE.CylinderGeometry(0.17, 0.17, 0.025, 56),
        new THREE.MeshStandardMaterial({color: c(0xdde6ef), roughness: 0.5}));
      deck.position.y = 0.19;
      const wheelMaterial = new THREE.MeshStandardMaterial({color: c(0x1b2230), roughness: 0.8});
      const wheels = [-0.215, 0.215].map(z => {
        const wheel = new THREE.Mesh(new THREE.CylinderGeometry(0.065, 0.065, 0.05, 28), wheelMaterial);
        wheel.rotation.x = Math.PI / 2;
        wheel.position.set(-0.02, 0.065, z);
        return wheel;
      });
      const puck = new THREE.Mesh(new THREE.CylinderGeometry(0.055, 0.06, 0.05, 32),
        new THREE.MeshStandardMaterial({color: c(0x1c2433), roughness: 0.35, metalness: 0.4}));
      puck.position.set(-0.04, 0.23, 0);
      this.scanner = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.012, 0.012),
        new THREE.MeshBasicMaterial({color: c(0xff3857)}));
      this.scanner.position.set(-0.04, 0.262, 0);
      const head = box(0.1, 0.075, 0.15, 0x1c2433);
      head.position.set(0.11, 0.25, 0);
      const lens = new THREE.Mesh(new THREE.CylinderGeometry(0.026, 0.026, 0.02, 24),
        new THREE.MeshStandardMaterial({color: c(0x6f86ff), roughness: 0.15, metalness: 0.6}));
      lens.rotation.z = Math.PI / 2;
      lens.position.set(0.168, 0.25, 0);
      const arrow = new THREE.ArrowHelper(new THREE.Vector3(1, 0, 0),
        new THREE.Vector3(0, 0.34, 0), 0.45, c(0x7c93ff), 0.11, 0.08);
      this.pulse = new THREE.Mesh(new THREE.RingGeometry(0.26, 0.31, 56),
        new THREE.MeshBasicMaterial({color: c(0x7ee0c6), transparent: true, opacity: 0, side: THREE.DoubleSide}));
      this.pulse.rotation.x = -Math.PI / 2;
      this.pulse.position.y = 0.012;
      for (const part of [body, deck, puck, ...wheels, lens]) { part.castShadow = true; part.receiveShadow = true; }
      this.robot.add(body, deck, puck, this.scanner, head, lens, arrow, this.pulse, ...wheels);
      // Movement history: poses are taken from recorded frames only; nothing is computed here.
      this.frames = [];
      this.recorded = false;
      this.index = 0;
      this.movement = null;
      this.onMovement = null;
      this.trail = new THREE.Group();
      this.scene.add(this.trail);
      this.from = new THREE.Vector3();
      this.to = new THREE.Vector3();
      this.startAngle = 0;
      this.angleDelta = 0;
      this.start = 0;
      this.duration = 0;
      this.born = [];
      this.reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
      this.resize = new ResizeObserver(() => {
        const {clientWidth: width, clientHeight: height} = canvas;
        if (!width || !height) return;
        this.renderer.setSize(width, height, false);
        this.camera.aspect = width / height;
        this.camera.updateProjectionMatrix();
      });
      this.resize.observe(canvas);
      canvas.addEventListener("pointerdown", event => {
        if (this.mode !== "orbit") return;
        this.drag = [event.clientX, event.clientY];
        canvas.setPointerCapture(event.pointerId);
      });
      const release = () => { this.drag = null; };
      canvas.addEventListener("pointerup", release);
      canvas.addEventListener("pointercancel", release);
      canvas.addEventListener("pointermove", event => {
        if (!this.drag) return;
        this.azimuth += (event.clientX - this.drag[0]) * 0.009;
        this.elevation = Math.min(1.48, Math.max(0.18, this.elevation + (event.clientY - this.drag[1]) * 0.009));
        this.drag = [event.clientX, event.clientY];
      });
      canvas.addEventListener("wheel", event => {
        if (this.mode !== "orbit") return;
        event.preventDefault();
        this.distance = Math.min(14, Math.max(1.8, this.distance + event.deltaY * 0.004));
      }, {passive: false});
      requestAnimationFrame(this.render);
    }

    setMode(mode) {
      this.mode = mode;
    }

    setRecording(frames) {
      this.frames = frames || [];
      this.recorded = Boolean(frames);
    }

    locate(frame) {
      if (!frame) return -1;
      if (!this.recorded) {
        if (frame.step === 0) this.frames = [];
        if (!this.frames.includes(frame)) this.frames.push(frame);
      }
      return this.frames.indexOf(frame);
    }

    /* Describe what the robot did in frame i, using only recorded poses and the recorded tool result. */
    analyse(i) {
      const frame = this.frames[i];
      if (!frame) return null;
      const pose = f => f.world.robot;
      let travelled = 0;
      for (let k = 1; k <= i; k++) {
        const a = pose(this.frames[k - 1]), b = pose(this.frames[k]);
        travelled += Math.hypot(b.x - a.x, b.y - a.y);
      }
      const tool = frame.tool;
      const total = `${Math.round(travelled)} cm travelled this run`;
      if (i === 0 || !tool) {
        return {state: "idle", text: `STATIONARY: initial pose, ${total}`, travelled};
      }
      const prev = pose(this.frames[i - 1]), now = pose(frame);
      const step = Math.hypot(now.x - prev.x, now.y - prev.y);
      const turn = Math.abs(((now.heading_deg - prev.heading_deg + 540) % 360) - 180);
      const isMove = ["move_forward", "move_backward", "turn"].includes(tool.name);
      const asked = tool.args?.distance_cm != null ? ` ${tool.args.distance_cm} cm` : tool.args?.degrees != null ? ` ${tool.args.degrees} deg` : "";
      if (isMove && !tool.ok) {
        const message = tool.result?.error?.message || "";
        const recheck = message.toLowerCase().includes("recheck before action");
        return {state: "cancelled", travelled, text: recheck
          ? `NOT MOVING: ${tool.name}${asked} was cancelled by the recheck. The robot did not move. ${total}`
          : `NOT MOVING: ${tool.name}${asked} was rejected. The robot did not move. ${total}`};
      }
      if (isMove && step > 0.5) {
        return {state: "moving", travelled, text: `MOVING: ${tool.name}${asked}. Travelled ${Math.round(step)} cm this step. ${total}`};
      }
      if (isMove && turn > 0.5) {
        return {state: "moving", travelled, text: `TURNING: ${tool.name}${asked}. Heading now ${now.heading_deg} deg. ${total}`};
      }
      if (isMove) {
        return {state: "idle", travelled, text: `NOT MOVING: ${tool.name}${asked} ran but the pose did not change. ${total}`};
      }
      const kind = tool.name.startsWith("read_") || tool.name === "get_position" ? "a sensor read" : "a memory operation";
      return {state: "idle", travelled, text: `STATIONARY: ${tool.name} is ${kind}. The robot did not move. ${total}`};
    }

    drawTrail(i) {
      clear(this.trail);
      if (i < 0) return;
      const poses = this.frames.slice(0, i + 1).map(f => f.world.robot);
      if (!poses.length) return;
      const start = poses[0];
      const ring = new THREE.Mesh(new THREE.RingGeometry(0.17, 0.2, 40),
        new THREE.MeshBasicMaterial({color: c(0xaab7cf), transparent: true, opacity: 0.55, side: THREE.DoubleSide}));
      ring.rotation.x = -Math.PI / 2;
      ring.position.copy(point(start.x, start.y, 0.012));
      this.trail.add(ring);
      const path = poses.filter((p, k) => k === 0 || p.x !== poses[k - 1].x || p.y !== poses[k - 1].y);
      if (path.length > 1) {
        this.trail.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(path.map(p => point(p.x, p.y, 0.03))),
          new THREE.LineBasicMaterial({color: c(0x7ee0c6)})));
      }
    }

    show(frame, animate = true) {
      const previous = this.frame;
      this.frame = frame;
      this.index = this.locate(frame);
      this.movement = this.analyse(this.index);
      this.updateHUD();
      this.drawTrail(this.index);
      if (this.onMovement) this.onMovement(this.movement);
      if (!this.renderer || !frame) return;
      const {world, tool} = frame;
      this.start = performance.now();
      this.from.copy(this.robot.position);
      this.to.copy(point(world.robot.x, world.robot.y));
      this.startAngle = this.robot.rotation.y;
      const target = heading(world.robot.heading_deg);
      this.angleDelta = Math.atan2(Math.sin(target - this.startAngle), Math.cos(target - this.startAngle));
      const moved = this.from.distanceToSquared(this.to) > 1e-10;
      const turned = Math.abs(this.angleDelta) > 1e-6;
      this.duration = previous && animate && !this.reduced ? (moved ? 600 : turned ? 300 : 0) : 0;
      const existing = new Set(previous?.world.obstacles.map(obstacle => obstacle.id));
      this.drawWorld(world, previous && animate && !this.reduced ? existing : null);
      this.drawReading(world, tool);
    }

    updateHUD() {
      const frame = this.frame;
      if (!frame) {
        this.hud.textContent = "Waiting for a recorded world frame.";
        return;
      }
      const {world, tool} = frame;
      const current = tool ? `${tool.name}${tool.auto ? " (automatic)" : ""}` : "initial";
      const readings = world.sensors;
      const distance = reading => reading ? `${reading.value} ${reading.unit || "cm"} · ${reading.status}` : "—";
      const camera = readings.camera_front;
      const seen = camera ? camera.value?.color ? `${camera.value.color} (${Number(camera.confidence).toFixed(2)})` : "nothing in view" : "—";
      this.hud.textContent = [
        `${world.scenario || "world"} · step ${frame.step} · ${current}`,
        `LiDAR ${distance(readings.lidar_front)}  |  Ultrasonic ${distance(readings.ultrasonic_front)}  |  Camera ${seen}`,
        `Pose ${world.robot.x}, ${world.robot.y} cm · ${world.robot.heading_deg}°`,
        this.movement ? this.movement.text : "",
      ].filter(Boolean).join("\n");
    }

    drawWorld(world, previous) {
      clear(this.world);
      this.born = [];
      const bounds = world.bounds_cm;
      const lowerX = Math.floor(bounds.x_min / 50) * 50;
      const upperX = Math.ceil(bounds.x_max / 50) * 50;
      const lowerY = Math.floor(bounds.y_min / 50) * 50;
      const upperY = Math.ceil(bounds.y_max / 50) * 50;
      const floor = box(cm(upperX - lowerX + 200), 0.05, cm(upperY - lowerY + 200), 0x2a374b);
      floor.material.roughness = 0.94;
      floor.castShadow = false;
      floor.position.copy(point((upperX + lowerX) / 2, (upperY + lowerY) / 2, -0.028));
      this.world.add(floor);
      const border = [point(lowerX, lowerY, 0.004), point(upperX, lowerY, 0.004), point(upperX, upperY, 0.004),
        point(lowerX, upperY, 0.004), point(lowerX, lowerY, 0.004)];
      this.world.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(border),
        new THREE.LineBasicMaterial({color: c(0x7f95b8)})));
      const centre = point((upperX + lowerX) / 2, (upperY + lowerY) / 2);
      const span = cm(Math.max(upperX - lowerX, upperY - lowerY)) / 2 + 1.5;
      this.key.position.set(centre.x + 2, 5, centre.z + 3);
      this.key.target.position.copy(centre);
      Object.assign(this.key.shadow.camera, {left: -span, right: span, top: span, bottom: -span, near: 0.5, far: 14});
      this.key.shadow.camera.updateProjectionMatrix();
      const grid = [];
      for (let x = lowerX; x <= upperX; x += 50) grid.push(point(x, lowerY, 0.002), point(x, upperY, 0.002));
      for (let y = lowerY; y <= upperY; y += 50) grid.push(point(lowerX, y, 0.002), point(upperX, y, 0.002));
      this.world.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(grid),
        new THREE.LineBasicMaterial({color: c(0x46566e), transparent: true, opacity: 0.65})));
      const warm = world.lighting.color === "yellow";
      this.light.color.copy(c(warm ? 0xffde77 : 0xdfe9ff));
      this.key.color.copy(c(warm ? 0xffd36b : 0xffffff));
      for (const obstacle of world.obstacles) {
        const glass = obstacle.material === "glass";
        const opacity = glass ? 0.25 : 1;
        const mesh = box(cm(obstacle.x_max - obstacle.x_min), 0.5,
          cm(obstacle.y_max - obstacle.y_min), glass ? 0x92dfff : 0x7d8696, opacity);
        mesh.position.copy(point((obstacle.x_min + obstacle.x_max) / 2,
          (obstacle.y_min + obstacle.y_max) / 2, 0.25));
        outline(mesh, glass ? 0xc3ebff : 0x505867);
        this.world.add(mesh);
        if (previous && !previous.has(obstacle.id) && obstacle.added_at_step != null) {
          mesh.material.transparent = true;
          this.born.push({mesh, opacity});
        }
      }
      for (const obj of world.objects) {
        const size = cm(obj.size_cm || 30);
        const mesh = box(size, size, size, colors[obj.true_color] ?? colors.white);
        mesh.position.copy(point(obj.x, obj.y, size / 2));
        this.world.add(mesh);
      }
    }

    drawReading(world, tool) {
      clear(this.cast);
      if (!tool) return;
      this.cast.position.copy(point(world.robot.x, world.robot.y));
      const direction = tool.args?.direction || "front";
      this.cast.rotation.y = heading(world.robot.heading_deg + (headings[direction] ?? 0));
      if (!tool.ok && ["move_forward", "move_backward"].includes(tool.name)) {
        const ring = new THREE.Mesh(new THREE.RingGeometry(0.25, 0.33, 40),
          new THREE.MeshBasicMaterial({color: c(0xff435d), transparent: true, opacity: 0.87, side: THREE.DoubleSide}));
        ring.rotation.x = -Math.PI / 2;
        ring.position.y = 0.021;
        ring.userData.baseOpacity = ring.material.opacity;
        this.cast.add(ring);
        return;
      }
      if (!tool.ok) return;
      const sensors = world.sensors;
      if (tool.name === "read_lidar") {
        const reading = sensors[`lidar_${direction}`];
        if (!reading || !Number.isFinite(reading.value)) return;
        const length = cm(Math.min(reading.value, reading.range_cm || 400));
        const opacity = reading.status === "blocked" ? 1 : 0.52;
        const beam = new THREE.Mesh(new THREE.CylinderGeometry(0.015, 0.015, length, 8),
          new THREE.MeshBasicMaterial({color: c(0xff3857), opacity, transparent: true}));
        beam.rotation.z = Math.PI / 2;
        beam.position.set(length / 2, 0.3, 0);
        this.cast.add(beam);
        const lidarLabel = observationLabel(`lidar: ${reading.value} cm (${reading.status})`);
        lidarLabel.position.set(Math.max(length, 0.5), 0.62, 0);
        lidarLabel.scale.multiplyScalar(0.7);
        this.cast.add(lidarLabel);
        if (reading.status === "blocked") {
          const hit = new THREE.Mesh(new THREE.SphereGeometry(0.055, 12, 12),
            new THREE.MeshBasicMaterial({color: c(0xff3857), transparent: true}));
          hit.position.set(length, 0.3, 0);
          this.cast.add(hit);
        }
      } else if (tool.name === "read_ultrasonic") {
        const reading = sensors.ultrasonic_front;
        if (reading && Number.isFinite(reading.value)) {
          const fan = cone(cm(reading.value), heading(7.5), 0x6fe89d, 0.63);
          fan.position.y = 0.35;
          this.cast.add(fan);
          const stop = cm(reading.value);
          const hit = new THREE.Mesh(new THREE.SphereGeometry(0.05, 12, 12),
            new THREE.MeshBasicMaterial({color: c(0x6fe89d), transparent: true}));
          hit.position.set(stop, 0.35, 0);
          this.cast.add(hit);
          const label = observationLabel(`ultrasonic: ${reading.value} cm (${reading.status})`);
          label.position.set(Math.max(stop, 0.5), 0.85, 0);
          label.scale.multiplyScalar(0.7);
          this.cast.add(label);
        }
      } else if (tool.name === "read_camera" && sensors.camera_front) {
        const reading = sensors.camera_front;
        const fan = cone(cm(reading.range_cm || 300), heading((reading.fov_deg || 60) / 2),
          reading.value?.color ? 0x7c93ff : 0x999faf, 0.3);
        this.cast.add(fan);
        if (!reading.value?.color) {
          const empty = observationLabel("camera: nothing in view");
          empty.position.set(1.5, 0.55, 0);
          empty.scale.multiplyScalar(0.7);
          this.cast.add(empty);
        }
        const found = world.objects.find(item => item.object_id === reading.value?.object_id && reading.value?.color);
        if (found) {
          const size = cm(found.size_cm || 30) + 0.04;
          const mark = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(size, size, size)),
            new THREE.LineBasicMaterial({color: c(0xc4d0ff)}));
          mark.position.copy(point(found.x, found.y, size / 2));
          this.world.add(mark);
          const label = observationLabel(`camera: ${reading.value.color} (${Number(reading.confidence).toFixed(2)})`);
          label.position.copy(point(found.x, found.y, size + 0.19));
          this.world.add(label);
        }
      }
      this.cast.traverse(item => {
        if (item.material) item.userData.baseOpacity = item.material.opacity;
      });
    }

    render = now => {
      requestAnimationFrame(this.render);
      if (!this.frame) return;
      const elapsed = now - this.start;
      const mix = this.duration ? Math.min(1, Math.max(0, elapsed / this.duration)) : 1;
      if (this.scanner) this.scanner.rotation.y = now / 140;
      if (this.pulse) {
        const active = this.movement && this.movement.state === "moving" && this.duration && mix < 1;
        this.pulse.material.opacity = active ? 0.55 + 0.35 * Math.sin(elapsed / 70) : 0;
      }
      this.robot.position.lerpVectors(this.from, this.to, mix);
      this.robot.rotation.y = this.startAngle + this.angleDelta * mix;
      for (const {mesh, opacity} of this.born) {
        mesh.material.opacity = opacity * Math.min(1, Math.max(0.12, elapsed / 500));
        mesh.material.emissive.setHex(0xe68536);
        mesh.material.emissiveIntensity = Math.max(0, 1 - elapsed / 1000) * (0.65 + 0.35 * Math.sin(elapsed / 58));
      }
      this.cast.traverse(item => {
        if (item.material && item.userData.baseOpacity != null) {
          item.material.opacity = item.userData.baseOpacity * Math.max(0, 1 - elapsed / 1500);
        }
      });
      const pos = this.robot.position;
      if (this.mode === "follow") {
        const rot = this.robot.rotation.y;
        const dx = Math.cos(rot), dz = -Math.sin(rot);
        this.camera.position.set(pos.x - 1.45 * dx + 0.9 * dz, 1.28, pos.z - 1.45 * dz - 0.9 * dx);
        this.camera.lookAt(pos.x + 1.3 * dx, 0.12, pos.z + 1.3 * dz);
      } else if (this.mode === "top") {
        const b = this.frame.world.bounds_cm;
        const x = cm((b.x_min + b.x_max) / 2), z = -cm((b.y_min + b.y_max) / 2);
        const span = cm(Math.max((b.x_max - b.x_min) / this.camera.aspect, b.y_max - b.y_min));
        this.camera.position.set(x, Math.max(3, span * 1.4), z + 0.01);
        this.camera.lookAt(x, 0, z);
      } else {
        const focus = pos.clone().add(new THREE.Vector3(1.3, 0.1, 0));
        const radius = this.distance * Math.cos(this.elevation);
        this.camera.position.set(focus.x + radius * Math.cos(this.azimuth),
          this.distance * Math.sin(this.elevation), focus.z + radius * Math.sin(this.azimuth));
        this.camera.lookAt(focus);
      }
      this.renderer.render(this.scene, this.camera);
    };
  }

  window.WorldViewer = WorldViewer;
})();
