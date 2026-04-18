from controller import Supervisor
import math

# ===============================
# BASIC SETTINGS
# ===============================
TIMESTEP = 16

# Moderate diagonal gait to reduce body wobble and solver stress.
GAIT_FREQ = 0.58

# Standing pose — knees bent so feet keep stable contact
HIP_FRONT_STAND = 0.24
HIP_REAR_STAND = 0.20
KNEE_STAND = -1.00

# Walking amplitudes and timing (static crawl)
HIP_FORWARD_EXT = 0.17
HIP_BACK_EXT = 0.19
KNEE_LIFT = 0.24

RAMP_TIME = 2.5          # Smoothly ramp walking motion from stand

SETTLE_TIME = 2.0

PAIR_A = {"fl", "br"}
PAIR_B = {"fr", "bl"}

# In this robot model, FL+BR have opposite sign from FR+BL.
HIP_SIGN = {
    "fl": -1.0,
    "fr": 1.0,
    "bl": 1.0,
    "br": -1.0,
}

# If the inferred forward direction is wrong for this world/proto orientation,
# this multiplier is flipped automatically after a short no-motion window.
FORWARD_SIGN = 1.0

ROLL_KP = 0.22
ROLL_CORR_MAX = 0.08
BALANCE_ROLL_LIMIT = 0.15
RIGHTING_ROLL_LIMIT = 0.20
RIGHTING_PITCH_LIMIT = 0.20

def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def hip_cmd(leg, angle_mag):
    return clamp(HIP_SIGN[leg] * FORWARD_SIGN * angle_mag, -0.8, 0.8)


def hip_stand_mag(leg):
    if leg in ("fl", "fr"):
        return HIP_FRONT_STAND
    return HIP_REAR_STAND


LEG_STRIDE_GAIN = {
    "fl": 1.00,
    "fr": 1.00,
    "bl": 1.08,
    "br": 1.08,
}


def roll_corrected_hip_position(leg, hip_mag_target, roll):
    pos = hip_cmd(leg, hip_mag_target)
    corr = clamp(-ROLL_KP * roll, -ROLL_CORR_MAX, ROLL_CORR_MAX)
    if leg in ("fl", "bl"):
        pos += corr
    else:
        pos -= corr
    return clamp(pos, -0.8, 0.8)


def apply_stand_pose(roll):
    for leg in legs:
        hips[leg].setPosition(roll_corrected_hip_position(leg, hip_stand_mag(leg), roll))
        knees[leg].setPosition(clamp(KNEE_STAND, -1.5, 0.1))


def apply_righting_pose(roll, t):
    phase = int((t * 2.0) % 2.0)
    tuck = -1.25
    extend = -0.85
    if phase == 0:
        hips["fl"].setPosition(roll_corrected_hip_position("fl", 0.34, roll))
        hips["br"].setPosition(roll_corrected_hip_position("br", 0.34, roll))
        hips["fr"].setPosition(roll_corrected_hip_position("fr", 0.12, roll))
        hips["bl"].setPosition(roll_corrected_hip_position("bl", 0.12, roll))
    else:
        hips["fl"].setPosition(roll_corrected_hip_position("fl", 0.12, roll))
        hips["br"].setPosition(roll_corrected_hip_position("br", 0.12, roll))
        hips["fr"].setPosition(roll_corrected_hip_position("fr", 0.34, roll))
        hips["bl"].setPosition(roll_corrected_hip_position("bl", 0.34, roll))

    for leg in ("fl", "br"):
        knees[leg].setPosition(tuck)
    for leg in ("fr", "bl"):
        knees[leg].setPosition(extend)

# ===============================
# INIT
# ===============================
robot = Supervisor()
TIMESTEP = int(robot.getBasicTimeStep())
legs = ["fl", "fr", "bl", "br"]

hips  = {}
knees = {}
hip_sensors = {}
knee_sensors = {}

for leg in legs:
    hip  = robot.getDevice(f"{leg}_hip")
    knee = robot.getDevice(f"{leg}_knee")
    hip_sensor = robot.getDevice(f"{leg}_hip_sensor")
    knee_sensor = robot.getDevice(f"{leg}_knee_sensor")

    # Higher velocity helps transitions without dragging feet.
    hip.setVelocity(3.0)
    knee.setVelocity(3.0)
    hip.setAvailableTorque(18.0)
    knee.setAvailableTorque(18.0)

    hip_sensor.enable(TIMESTEP)
    knee_sensor.enable(TIMESTEP)

    hips[leg]  = hip
    knees[leg] = knee
    hip_sensors[leg] = hip_sensor
    knee_sensors[leg] = knee_sensor

imu = robot.getDevice("imu")
imu.enable(TIMESTEP)

gps = robot.getDevice("gps")
gps.enable(TIMESTEP)

robot_node = robot.getFromDef("QUADRUPED")
robot_translation = robot_node.getField("translation")
robot_rotation = robot_node.getField("rotation")
robot_translation0 = [0.0, 0.31, 0.0]
robot_rotation0 = [0.0, 1.0, 0.0, 0.0]

def respawn_upright():
    robot_translation.setSFVec3f(robot_translation0)
    robot_rotation.setSFRotation(robot_rotation0)
    for leg in legs:
        hips[leg].setVelocity(0.0)
        knees[leg].setVelocity(0.0)
        hips[leg].setPosition(hip_stand_mag(leg))
        knees[leg].setPosition(KNEE_STAND)

# Warm up sensors
for _ in range(20):
    robot.step(TIMESTEP)

# ===============================
# PHASE 1 — SLOW CROUCH DOWN
# Moves knees first, then hips, so the robot lowers itself
# evenly and doesn't topple.
# ===============================
print("Crouching...")
CROUCH_STEPS = int(1.5 / (TIMESTEP / 1000))   # 1.5 s
initial_hip = {leg: hip_sensors[leg].getValue() for leg in legs}
initial_knee = {leg: knee_sensors[leg].getValue() for leg in legs}

for i in range(CROUCH_STEPS):
    robot.step(TIMESTEP)
    alpha = i / CROUCH_STEPS                   # 0 → 1

    for leg in legs:
        # Interpolate from current saved pose to desired standing pose.
        h0 = initial_hip[leg]
        k0 = initial_knee[leg]
        h1 = hip_cmd(leg, hip_stand_mag(leg))
        k1 = KNEE_STAND

        h = (1.0 - alpha) * h0 + alpha * h1
        k = (1.0 - alpha) * k0 + alpha * k1

        hips[leg].setPosition(clamp(h, -0.8, 0.8))
        knees[leg].setPosition(clamp(k, -1.5, 0.1))

# ===============================
# PHASE 2 — HOLD & SETTLE
# ===============================
print("Standing...")
SETTLE_STEPS = int(SETTLE_TIME / (TIMESTEP / 1000))

for _ in range(SETTLE_STEPS):
    robot.step(TIMESTEP)
    roll, _, _ = imu.getRollPitchYaw()
    for leg in legs:
        hips[leg].setPosition(roll_corrected_hip_position(leg, hip_stand_mag(leg), roll))
        knees[leg].setPosition(clamp(KNEE_STAND, -1.5, 0.1))

print("Walking started!")
walk_start_time = robot.getTime()
start_pos = gps.getValues()
last_print = 0
direction_checked = False

# ===============================
# PHASE 3 — WALK LOOP
# ===============================
while robot.step(TIMESTEP) != -1:

    t = robot.getTime()
    roll, pitch, _ = imu.getRollPitchYaw()
    orientation = robot_node.getOrientation()
    up_z = orientation[8]

    if up_z < 0.0:
        print(f"[RESET] upside down detected, respawning upright (up_z={up_z:.2f})")
        respawn_upright()
        walk_start_time = robot.getTime()
        start_pos = gps.getValues()
        last_print = 0
        direction_checked = False
        continue

    # ---- Recovery mode: actively right the body before it fully falls ----
    if abs(roll) > RIGHTING_ROLL_LIMIT or abs(pitch) > RIGHTING_PITCH_LIMIT or gps.getValues()[1] < 0.25:
        print(f"[RIGHTING] roll={math.degrees(roll):.1f} pitch={math.degrees(pitch):.1f} y={gps.getValues()[1]:.3f}")
        apply_righting_pose(roll, t)
        continue

    ramp = clamp((t - walk_start_time) / RAMP_TIME, 0.0, 1.0)
    knee_lift = KNEE_LIFT * ramp

    # If lateral tilt is high, keep a stabilizing stance and wait to recover.
    if abs(roll) > BALANCE_ROLL_LIMIT:
        apply_stand_pose(roll)
        continue

    p = (t * GAIT_FREQ) % 1.0
    if p < 0.5:
        swing_pair = PAIR_A
        stance_pair = PAIR_B
        u = p / 0.5
    else:
        swing_pair = PAIR_B
        stance_pair = PAIR_A
        u = (p - 0.5) / 0.5

    for leg in legs:
        stride = LEG_STRIDE_GAIN[leg]

        if leg in swing_pair:
            # Swing: move foot from back to front while lifting.
            hip_target = hip_stand_mag(leg) + stride * (-HIP_BACK_EXT + (HIP_FORWARD_EXT + HIP_BACK_EXT) * u) * ramp
            knee_target = KNEE_STAND - knee_lift * math.sin(math.pi * u)
        else:
            # Stance: keep foot down and push from front to back.
            hip_target = hip_stand_mag(leg) + stride * (HIP_FORWARD_EXT - (HIP_FORWARD_EXT + HIP_BACK_EXT) * u) * ramp
            knee_target = KNEE_STAND

        hips[leg].setPosition(roll_corrected_hip_position(leg, hip_target, roll))
        knees[leg].setPosition(clamp(knee_target, -1.5, 0.1))

    # ---- Debug print every second ----
    if t - last_print > 1.0:
        pos = gps.getValues()
        dx = pos[0] - start_pos[0]
        dz = pos[2] - start_pos[2]
        dist = math.hypot(dx, dz)

        # One-time fallback: if almost no translation after gait ramp, try the
        # opposite hip direction mapping.
        if (not direction_checked) and (t - walk_start_time > RAMP_TIME + 5.0):
            direction_checked = True
            if dist < 0.01:
                FORWARD_SIGN = -1.0
                start_pos = pos
                walk_start_time = t
                print("[AUTO-TUNE] No motion detected, flipping FORWARD_SIGN and retrying gait")

        print(
            f"x={pos[0]:.3f} y={pos[1]:.3f} z={pos[2]:.3f} | "
            f"dx={dx:.3f} dz={dz:.3f} dist={dist:.3f} | "
            f"roll={math.degrees(roll):.1f}  pitch={math.degrees(pitch):.1f}"
        )
        last_print = t