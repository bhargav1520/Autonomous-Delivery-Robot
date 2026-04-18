from controller import Supervisor
import math

TIMESTEP = 8

HIP_NAMES = [
    "hip_motor_l0",
    "hip_motor_l1",
    "hip_motor_l2",
    "hip_motor_r0",
    "hip_motor_r1",
    "hip_motor_r2",
]

KNEE_NAMES = [
    "knee_motor_l0",
    "knee_motor_l1",
    "knee_motor_l2",
    "knee_motor_r0",
    "knee_motor_r1",
    "knee_motor_r2",
]

# Alternating tripod gait groups from the Webots example.
TRIPOD_A = ["l0", "r1", "l2"]
TRIPOD_B = ["r0", "l1", "r2"]

HIP_SIGN = {
    "l0": 1.0,
    "l1": 1.0,
    "l2": 1.0,
    "r0": -1.0,
    "r1": -1.0,
    "r2": -1.0,
}

PHASE_OFFSET = {
    "l0": 0.0,
    "r1": 0.0,
    "l2": 0.0,
    "r0": 0.5,
    "l1": 0.5,
    "r2": 0.5,
}

robot = Supervisor()
if robot.getBasicTimeStep() > 0:
    TIMESTEP = int(robot.getBasicTimeStep())

keyboard = robot.getKeyboard()
keyboard.enable(TIMESTEP)

# Build a lowercase name -> device map so optional sensor lookup does not
# trigger Webots "device not found" warnings.
device_by_name = {}
for i in range(robot.getNumberOfDevices()):
    dev = robot.getDeviceByIndex(i)
    device_by_name[dev.getName().lower()] = dev

imu = None
for name in ("imu", "inertial unit", "inertial_unit", "IMU"):
    candidate = device_by_name.get(name.lower())
    if candidate is not None:
        imu = candidate
        break
if imu is not None:
    imu.enable(TIMESTEP)

gps = None
for name in ("gps", "GPS"):
    candidate = device_by_name.get(name.lower())
    if candidate is not None:
        gps = candidate
        break
if gps is not None:
    gps.enable(TIMESTEP)

hips = {}
knees = {}
legs = ["l0", "l1", "l2", "r0", "r1", "r2"]

for leg in legs:
    hip = robot.getDevice(f"hip_motor_{leg}")
    knee = robot.getDevice(f"knee_motor_{leg}")
    hip.setVelocity(3.0)
    knee.setVelocity(0.04)
    hips[leg] = hip
    knees[leg] = knee

# Start from a low, stable crouched stance.
HIP_STAND = 0.06
HIP_FORWARD = 0.18
HIP_BACK = 0.16
KNEE_STANCE = -0.016
KNEE_SWING = -0.012
GAIT_PERIOD = 2.1
RAMP_TIME = 7.0
STANCE_RATIO = 0.70

SIDE_GAIN = {
    "l0": 1.00,
    "l1": 1.00,
    "l2": 1.00,
    "r0": 1.00,
    "r1": 1.00,
    "r2": 1.00,
}

MODE_STOP = "STOP"
MODE_FORWARD = "FORWARD"
MODE_LEFT = "LEFT"
MODE_RIGHT = "RIGHT"

NAV_MODE_AUTO = "AUTO"
NAV_MODE_MANUAL = "MANUAL"

mode = MODE_STOP
auto_available = (imu is not None) and (gps is not None)
nav_mode = NAV_MODE_AUTO if auto_available else NAV_MODE_MANUAL

TARGET_BLOCK = (3.95, 0.10)
PICKUP_POINT = TARGET_BLOCK
DROP_POINT = (1.55, -1.40)
WAYPOINT_REACH_RADIUS = 0.10
AUTO_HEADING_OFFSET = 0.0
AUTO_FORWARD_SIGN = 1.0
AUTO_STEER_GAIN = math.radians(90.0)
AUTO_STEER_LIMIT = 0.22
AUTO_SIDE_BIAS_MIN = 0.70

DELIVERY_START = "TO_PICKUP"
DELIVERY_CARRY = "TO_DROPOFF"
DELIVERY_DONE = "DONE"
delivery_state = DELIVERY_START
carry_offset = 0.22
payload_height = 0.26

package_node = robot.getFromDef("DELIVERY_BLOCK")
package_translation = package_node.getField("translation") if package_node is not None else None
drop_marker_node = robot.getFromDef("DELIVERY_DROP_ZONE")
drop_marker_translation = drop_marker_node.getField("translation") if drop_marker_node is not None else None


def wrap_angle(angle):
    return math.atan2(math.sin(angle), math.cos(angle))


def clamp(value, lower, upper):
    return max(lower, min(upper, value))


def auto_drive_command(distance, heading_error):
    if distance < WAYPOINT_REACH_RADIUS:
        return MODE_STOP, 0.0

    steer = clamp(heading_error / AUTO_STEER_GAIN, -AUTO_STEER_LIMIT, AUTO_STEER_LIMIT)
    return MODE_FORWARD, steer


def parse_mode_from_key(key, current_mode):
    if key in (ord("w"), ord("W")):
        return MODE_FORWARD
    if key in (ord("a"), ord("A")):
        return MODE_LEFT
    if key in (ord("d"), ord("D")):
        return MODE_RIGHT
    if key in (ord("s"), ord("S")):
        return MODE_STOP
    return current_mode


def mode_gain(leg, current_mode):
    if current_mode == MODE_LEFT:
        return 0.55 if leg.startswith("l") else 1.0
    if current_mode == MODE_RIGHT:
        return 1.0 if leg.startswith("l") else 0.55
    if current_mode == MODE_STOP:
        return 0.0
    return 1.0

stance_start = robot.getTime()

for _ in range(int(1.5 * 1000 / TIMESTEP)):
    if robot.step(TIMESTEP) == -1:
        exit()
    t = robot.getTime()
    alpha = min((t - stance_start) / 2.5, 1.0)
    for leg in legs:
        hips[leg].setPosition(HIP_SIGN[leg] * (HIP_STAND * alpha))
        knees[leg].setPosition(KNEE_STANCE)

print("Hexapod started")
print("Controls: W=forward, A=left, D=right, S=stop")
if auto_available:
    print("Navigation: AUTO starts by default and handles pickup then drop-off")
    print("Navigation: press M to re-enter AUTO after manual control")
    print("Navigation: AUTO uses direct target heading with smooth steering")
    print(f"Pickup point: {PICKUP_POINT}")
    print(f"Drop-off point: {DROP_POINT}")
else:
    print("[INFO] IMU/GPS not available -> AUTO waypoint mode disabled, manual ASWD only")
walk_start = robot.getTime()
last_print = 0.0
last_nav_print = 0.0
auto_steer = 0.0


def update_payload_pose(robot_position, robot_yaw, carried):
    if package_translation is None:
        return
    if carried:
        package_x = robot_position[0] + carry_offset * math.cos(robot_yaw)
        package_z = robot_position[2] + carry_offset * math.sin(robot_yaw)
        package_translation.setSFVec3f([package_x, payload_height, package_z])


def set_payload_at(point):
    if package_translation is not None:
        package_translation.setSFVec3f([point[0], payload_height, point[1]])


if drop_marker_translation is not None:
    drop_marker_translation.setSFVec3f([DROP_POINT[0], 0.25, DROP_POINT[1]])

set_payload_at(PICKUP_POINT)
carrying_payload = False

while robot.step(TIMESTEP) != -1:
    auto_distance = None
    key = keyboard.getKey()
    while key != -1:
        if key in (ord("m"), ord("M")):
            if auto_available:
                nav_mode = NAV_MODE_AUTO
                auto_steer = 0.0
            else:
                print("[INFO] AUTO mode unavailable (missing IMU or GPS).")
        else:
            parsed = parse_mode_from_key(key, mode)
            if parsed != mode:
                mode = parsed
                nav_mode = NAV_MODE_MANUAL
        key = keyboard.getKey()

    t = robot.getTime()

    if auto_available and nav_mode == NAV_MODE_AUTO and delivery_state != DELIVERY_DONE:
        pos = gps.getValues()
        _, _, yaw = imu.getRollPitchYaw()

        if delivery_state == DELIVERY_START:
            target_x, target_z = PICKUP_POINT
        elif delivery_state == DELIVERY_CARRY:
            target_x, target_z = DROP_POINT
        else:
            target_x, target_z = DROP_POINT

        dx = target_x - pos[0]
        dz = target_z - pos[2]
        distance = math.hypot(dx, dz)
        auto_distance = distance

        if delivery_state == DELIVERY_START and distance < WAYPOINT_REACH_RADIUS:
            delivery_state = DELIVERY_CARRY
            carrying_payload = True
            mode = MODE_STOP
            auto_steer = 0.0
            print(f"[AUTO] Pickup reached at dist={distance:.2f}. Carrying payload to drop-off.")
        elif delivery_state == DELIVERY_CARRY and distance < WAYPOINT_REACH_RADIUS:
            delivery_state = DELIVERY_DONE
            carrying_payload = False
            mode = MODE_STOP
            auto_steer = 0.0
            set_payload_at(DROP_POINT)
            print(f"[AUTO] Drop-off reached at dist={distance:.2f}. Delivery complete.")

        if delivery_state != DELIVERY_DONE:
            desired_yaw = wrap_angle(math.atan2(dx, dz) + AUTO_HEADING_OFFSET)
            heading_error = wrap_angle(desired_yaw - yaw)
            mode, auto_steer = auto_drive_command(distance, heading_error)

            if t - last_nav_print > 0.5:
                print(
                    f"[AUTO] state={delivery_state} target=({target_x:.2f},{target_z:.2f}) "
                    f"dist={distance:.2f} yaw={math.degrees(yaw):.1f} "
                    f"err={math.degrees(heading_error):.1f} mode={mode} steer={auto_steer:.2f}"
                )
                last_nav_print = t
        else:
            auto_steer = 0.0
            mode = MODE_STOP

    phase_global = ((t - walk_start) % GAIT_PERIOD) / GAIT_PERIOD
    ramp = min((t - walk_start) / RAMP_TIME, 1.0)

    swing_group = []

    for leg in legs:
        phase = (phase_global + PHASE_OFFSET[leg]) % 1.0
        gain = SIDE_GAIN[leg] * mode_gain(leg, mode)

        if nav_mode == NAV_MODE_AUTO and mode == MODE_FORWARD:
            if leg.startswith("l"):
                gain *= clamp(1.0 - auto_steer, AUTO_SIDE_BIAS_MIN, 1.0 + AUTO_SIDE_BIAS_MIN)
            else:
                gain *= clamp(1.0 + auto_steer, AUTO_SIDE_BIAS_MIN, 1.0 + AUTO_SIDE_BIAS_MIN)

        if phase < STANCE_RATIO:
            # Stance: keep the foot on ground and push from front to back.
            u = phase / STANCE_RATIO
            hip_mag = gain * (HIP_FORWARD - (HIP_FORWARD + HIP_BACK) * u)
            knees[leg].setPosition(KNEE_STANCE)
        else:
            # Swing: lift and return foot from back to front.
            swing_group.append(leg)
            u = (phase - STANCE_RATIO) / (1.0 - STANCE_RATIO)
            hip_mag = gain * (-HIP_BACK + (HIP_FORWARD + HIP_BACK) * u)
            knees[leg].setPosition(KNEE_STANCE + (KNEE_SWING - KNEE_STANCE) * math.sin(math.pi * u))

        if nav_mode == NAV_MODE_AUTO and mode == MODE_FORWARD:
            hip_mag *= AUTO_FORWARD_SIGN

        hips[leg].setPosition(HIP_SIGN[leg] * (HIP_STAND + ramp * hip_mag))

    if carrying_payload and package_translation is not None and gps is not None and imu is not None:
        robot_position = gps.getValues()
        _, _, yaw = imu.getRollPitchYaw()
        update_payload_pose(robot_position, yaw, True)

    if t - last_print > 1.0:
        print(f"t={t:.2f} mode={mode} phase={phase_global:.2f} swing={','.join(swing_group)}")
        last_print = t
