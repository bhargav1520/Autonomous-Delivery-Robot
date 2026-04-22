"""
AUTONOMOUS DELIVERY ROBOT CONTROLLER
Webots Hexapod Robot with Complete Delivery System
Fixes all broken features and adds box system + mini-map
"""

import math
import datetime
from controller import Supervisor

# ===== CONSTANTS =====
TIME_STEP = 32
MAX_SPEED = 2.6
TURN_GAIN = 1.4
ARRIVE_THRESHOLD = 0.25
OBSTACLE_THRESHOLD = 0.5
EMERGENCY_STOP_THRESHOLD = 0.50
AVOID_MIN_STEPS = 30
AVOID_STOP_STEPS = 8
OBSTACLE_SIDE_THRESHOLD = 0.45
OBSTACLE_CONFIRM_STEPS = 2
BRAKE_THRESHOLD = 0.70
STUCK_PROGRESS_EPS = 0.002
STUCK_STEPS_TRIGGER = 45
AVOID_REVERSE_STEPS = 12
AVOID_TURN_STEPS = 18
ARENA_MIN_X = -4.8
ARENA_MAX_X = 4.8
ARENA_MIN_Z = -4.8
ARENA_MAX_Z = 4.8
BOUNDARY_MARGIN = 0.35
BOUNDARY_OUTWARD_DOT = 0.18
BOUNDARY_RECOVERY_STEPS = 220
BOUNDARY_REVERSE_STEPS = 28
CARRY_HEIGHT = 0.18
CARRY_AHEAD = 0.00
PAYLOAD_GROUND_Y = 0.09
PICKUP_AHEAD = 0.24
PICKUP_SIDE = 0.16
DELIVER_DURATION = int(3000 / TIME_STEP)  # 3 seconds in steps
BATTERY_LOW = 20.0
BATTERY_DRAIN_MOVING = 0.0015
BATTERY_DRAIN_IDLE = 0.0003
BATTERY_CHARGE_RATE = 0.05
HEADING_OFFSET = 0.0
MOTOR_MAX_CMD = 4.8
KNEE_MIN_POS = -0.02
KNEE_MAX_POS = 0.02
KNEE_STANCE_POS = -0.016

# Stable tripod gait constants.
HIP_STAND = 0.06
HIP_FORWARD = 0.20
HIP_BACK = 0.18
KNEE_LIFT_AMPL = 0.004
GAIT_PERIOD = 1.2
RAMP_TIME = 0.6
STANCE_RATIO = 0.70

BATTERY_PRINT_STEPS = 500

LEG_IDS = ["l0", "l1", "l2", "r0", "r1", "r2"]
PHASE_OFFSET = {
    "l0": 0.0,
    "r1": 0.0,
    "l2": 0.0,
    "r0": 0.5,
    "l1": 0.5,
    "r2": 0.5,
}
HIP_SIGN = {
    "l0": 1.0, "l1": 1.0, "l2": 1.0,
    "r0": -1.0, "r1": -1.0, "r2": -1.0,
}

# Waypoints: adjust x,z to match your actual hexapod.wbt world coordinates
WAYPOINTS = {
    "HOME":    (0.0,  0.0),
    "HOUSE_A": (2.0,  1.5),
    "HOUSE_B": (-2.0, 1.5),
    "HOUSE_C": (2.0, -1.5),
    "HOUSE_D": (-2.0, -1.5),
}

BOX_ORIGINS = {
    "BOX_A": (2.0,  0.05, 1.5),
    "BOX_B": (-2.0, 0.05, 1.5),
    "BOX_C": (2.0,  0.05, -1.5),
    "BOX_D": (-2.0, 0.05, -1.5),
}

# States
STATE_IDLE = "IDLE"
STATE_NAVIGATING = "NAVIGATING"
STATE_AVOIDING = "AVOIDING"
STATE_DELIVERING = "DELIVERING"
STATE_RETURNING = "RETURNING"
STATE_CHARGING = "CHARGING"


def log(msg):
    """Print message with timestamp"""
    timestamp = datetime.datetime.now().strftime('%H:%M:%S')
    print(f"[{timestamp}] {msg}")


# ===== NAVIGATION CLASS =====
class Navigation:
    """Handle GPS, compass, heading calculation, and waypoint navigation"""

    def __init__(self, robot):
        """Initialize GPS and compass devices"""
        self.gps = robot.getDevice("gps")
        self.compass = robot.getDevice("compass")
        
        if self.gps is None or self.compass is None:
            log("ERROR: GPS or Compass not found!")
            return
        
        self.gps.enable(TIME_STEP)
        self.compass.enable(TIME_STEP)

    def get_position(self):
        """Return ground-plane (x, y) from GPS, ignoring z (height)."""
        gps_val = self.gps.getValues()
        return (gps_val[0], gps_val[1])

    def get_heading(self):
        """Return heading angle (radians) from compass in x/y plane."""
        comp = self.compass.getValues()
        raw_heading = math.atan2(comp[0], comp[1])
        return self.normalize_angle(raw_heading + HEADING_OFFSET)

    def get_bearing(self, from_pos, to_pos):
        """Calculate bearing angle from one position to another"""
        dx = to_pos[0] - from_pos[0]
        dz = to_pos[1] - from_pos[1]
        return math.atan2(dx, dz)

    def normalize_angle(self, angle):
        """Normalize angle to [-pi, pi]"""
        while angle > math.pi:
            angle -= 2 * math.pi
        while angle < -math.pi:
            angle += 2 * math.pi
        return angle

    def calculate_steering(self, current_pos, heading, target_pos):
        """
        Calculate left/right motor speeds for navigation
        Returns: (left_speed, right_speed)
        """
        bearing = self.get_bearing(current_pos, target_pos)
        error = self.normalize_angle(bearing - heading)

        # Rotate in place if heading error is large
        if abs(error) > 0.15:
            left_speed = -TURN_GAIN * error
            right_speed = TURN_GAIN * error
            return (left_speed, right_speed)

        # Move forward with proportional steering
        forward = MAX_SPEED * max(0.3, 1.0 - abs(error))
        left_speed = forward - TURN_GAIN * error
        right_speed = forward + TURN_GAIN * error
        return (left_speed, right_speed)

    def has_arrived(self, current_pos, target_pos):
        """Check if robot reached waypoint (distance < ARRIVE_THRESHOLD)"""
        dx = target_pos[0] - current_pos[0]
        dz = target_pos[1] - current_pos[1]
        distance = math.sqrt(dx**2 + dz**2)
        return distance < ARRIVE_THRESHOLD


# ===== OBSTACLE DETECTOR CLASS =====
class ObstacleDetector:
    """Handle 4 distance sensors and avoidance logic"""

    def __init__(self, robot):
        """Initialize 4 distance sensors"""
        self.front = robot.getDevice("ds_front")
        self.left = robot.getDevice("ds_left")
        self.right = robot.getDevice("ds_right")
        self.back = robot.getDevice("ds_back")
        
        self.avoid_timer = 0
        self.is_avoiding = False
        self.blocked_count = 0
        self.clear_count = 0
        self.turn_dir = 1

        for sensor in [self.front, self.left, self.right, self.back]:
            if sensor is not None:
                sensor.enable(TIME_STEP)
            else:
                log("WARNING: One or more distance sensors not found")

    def update_readings(self):
        """Read all sensor values"""
        self.front_val = self.front.getValue() if self.front else 999
        self.left_val = self.left.getValue() if self.left else 999
        self.right_val = self.right.getValue() if self.right else 999
        self.back_val = self.back.getValue() if self.back else 999

    def is_blocked(self):
        """Check if front or near-side sensors detect obstacle."""
        if self.front_val <= 0.0:
            self.blocked_count = 0
            return False

        front_blocked = self.front_val < OBSTACLE_THRESHOLD
        side_blocked = min(self.left_val, self.right_val) < OBSTACLE_SIDE_THRESHOLD

        # Emergency trigger: stop immediately when obstacle is very close.
        emergency_blocked = (
            self.front_val < EMERGENCY_STOP_THRESHOLD
            or min(self.left_val, self.right_val) < (OBSTACLE_SIDE_THRESHOLD * 0.75)
        )

        if emergency_blocked:
            self.blocked_count = OBSTACLE_CONFIRM_STEPS
            return True

        if front_blocked or side_blocked:
            self.blocked_count += 1
        else:
            self.blocked_count = 0
        return self.blocked_count >= OBSTACLE_CONFIRM_STEPS

    def should_brake_now(self):
        """Emergency brake when any forward-facing sensor is too close."""
        # Ignore non-positive readings; some sensor models report 0 when out of range.
        candidates = [v for v in (self.front_val, self.left_val, self.right_val) if v > 0.0]
        if not candidates:
            return False
        return min(candidates) < BRAKE_THRESHOLD

    def start_avoidance(self, turn_dir=None):
        """Enter avoidance state"""
        self.is_avoiding = True
        self.avoid_timer = 0
        self.clear_count = 0
        # Optional turn override for boundary avoidance.
        if turn_dir in (-1, 1):
            self.turn_dir = turn_dir
        else:
            # Turn toward the side with more free space.
            self.turn_dir = -1 if self.left_val > self.right_val else 1

    def update_avoidance(self):
        """
        Update avoidance logic
        Returns: (should_continue_avoiding, (left_speed, right_speed))
        """
        self.avoid_timer += 1

        # Stage 0: hard stop before maneuvering away.
        if self.avoid_timer <= AVOID_STOP_STEPS:
            avoid_speed = (0.0, 0.0)
        # Stage 1: reverse to break physical contact with obstacle.
        elif self.avoid_timer <= (AVOID_STOP_STEPS + AVOID_REVERSE_STEPS):
            avoid_speed = (-0.80 * MAX_SPEED, -0.80 * MAX_SPEED)
        # Stage 2: strong turn to reorient away from obstacle.
        elif self.avoid_timer <= (AVOID_STOP_STEPS + AVOID_REVERSE_STEPS + AVOID_TURN_STEPS):
            if self.turn_dir < 0:
                avoid_speed = (-MAX_SPEED, MAX_SPEED)
            else:
                avoid_speed = (MAX_SPEED, -MAX_SPEED)
        # Stage 3: arc forward so robot changes path before returning to nav.
        else:
            if self.turn_dir < 0:
                avoid_speed = (0.55 * MAX_SPEED, 1.00 * MAX_SPEED)
            else:
                avoid_speed = (1.00 * MAX_SPEED, 0.55 * MAX_SPEED)

        # Only exit avoidance if timer >= minimum and front is clear
        if self.front_val > (OBSTACLE_THRESHOLD + 0.10):
            self.clear_count += 1
        else:
            self.clear_count = 0

        if self.avoid_timer >= AVOID_MIN_STEPS and self.clear_count >= 5:
            self.is_avoiding = False
            self.avoid_timer = 0
            self.clear_count = 0
            return (False, avoid_speed)

        return (True, avoid_speed)


# ===== BATTERY MANAGER CLASS =====
class BatteryManager:
    """Handle battery level, drain, and charging"""

    def __init__(self):
        """Initialize battery at 100%"""
        self.level = 100.0

    def update(self, state):
        """
        Update battery based on current state
        States: NAVIGATING/AVOIDING drain faster, DELIVERING/IDLE drain slower, CHARGING charges
        """
        if state in [STATE_NAVIGATING, STATE_AVOIDING]:
            self.level -= BATTERY_DRAIN_MOVING
        elif state in [STATE_DELIVERING, STATE_IDLE]:
            self.level -= BATTERY_DRAIN_IDLE
        elif state == STATE_RETURNING:
            self.level -= BATTERY_DRAIN_MOVING
        elif state == STATE_CHARGING:
            self.level += BATTERY_CHARGE_RATE

        # Clamp to [0, 100]
        self.level = max(0.0, min(100.0, self.level))

    def is_low(self):
        """Check if battery is below LOW threshold"""
        return self.level < BATTERY_LOW

    def is_full(self):
        """Check if battery is fully charged"""
        return self.level >= 100.0


# ===== MINIMAP DISPLAY CLASS =====
class MinimapDisplay:
    """Real-time mini-map on 200x200 Display device"""

    def __init__(self, robot):
        """Initialize display device"""
        self.display = robot.getDevice("display")
        if self.display is None:
            log("WARNING: Display device not found, mini-map disabled")
            self.enabled = False
        else:
            self.enabled = True
            self.display.setColor(0x000000)
            self.display.fillRectangle(0, 0, 200, 200)

        self.step_counter = 0
        self.WORLD_MIN = -4.0
        self.WORLD_MAX = 4.0

    def world_to_display(self, world_x, world_z):
        """Convert world coordinates to display pixel coordinates"""
        px = int((world_x - self.WORLD_MIN) / (self.WORLD_MAX - self.WORLD_MIN) * 200)
        py = int((world_z - self.WORLD_MIN) / (self.WORLD_MAX - self.WORLD_MIN) * 200)
        return (px, py)

    def update(self, robot_pos, heading, delivered_houses):
        """Update mini-map display"""
        if not self.enabled:
            return

        # Only update every 15 steps for performance
        self.step_counter += 1
        if self.step_counter % 15 != 0:
            return

        # Clear background
        self.display.setColor(0x000000)
        self.display.fillRectangle(0, 0, 200, 200)

        # Draw each waypoint
        colors = {
            "HOME": 0xFFFFFF,
            "HOUSE_A": 0xFF4444,
            "HOUSE_B": 0x4488FF,
            "HOUSE_C": 0x44FF88,
            "HOUSE_D": 0xFFDD00,
        }

        for name, pos in WAYPOINTS.items():
            px, py = self.world_to_display(pos[0], pos[1])
            
            # If already delivered, use gray
            if name in delivered_houses:
                self.display.setColor(0x555555)
            else:
                self.display.setColor(colors.get(name, 0xFFFFFF))

            # Draw waypoint circle (radius 6)
            self.display.fillOval(px - 6, py - 6, 12, 12)

        # Draw robot position as white circle with heading line
        px, py = self.world_to_display(robot_pos[0], robot_pos[1])
        self.display.setColor(0xFFFFFF)
        self.display.fillOval(px - 5, py - 5, 10, 10)

        # Draw heading line
        head_px = px + int(8 * math.cos(heading - math.pi/2))
        head_py = py + int(8 * math.sin(heading - math.pi/2))
        self.display.drawLine(px, py, head_px, head_py)


# ===== MAIN DELIVERY ROBOT CLASS =====
class DeliveryRobot:
    """Main robot controller with complete FSM"""

    def __init__(self):
        """Initialize robot, sensors, actuators, and state"""
        self.robot = Supervisor()
        
        # Devices
        self.navigation = Navigation(self.robot)
        self.obstacle_detector = ObstacleDetector(self.robot)
        self.battery_manager = BatteryManager()
        self.minimap = MinimapDisplay(self.robot)

        # Dynamic arena bounds (updated in calibrate_world_frame).
        self.arena_min_x = ARENA_MIN_X
        self.arena_max_x = ARENA_MAX_X
        self.arena_min_z = ARENA_MIN_Z
        self.arena_max_z = ARENA_MAX_Z
        
        # Keyboard
        self.keyboard = self.robot.getKeyboard()
        if self.keyboard:
            self.keyboard.enable(TIME_STEP)
        else:
            log("WARNING: Keyboard not available")

        # Motor naming in this world:
        # hip_motor_l0..l2, knee_motor_l0..l2, hip_motor_r0..r2, knee_motor_r0..r2
        self.hips = {}
        self.knees = {}

        for leg_id in LEG_IDS:
            side = leg_id[0]
            idx = leg_id[1]
            hip = self.robot.getDevice(f"hip_motor_{side}{idx}")
            knee = self.robot.getDevice(f"knee_motor_{side}{idx}")

            if hip is None:
                log(f"WARNING: Motor hip_motor_{side}{idx} not found")
                continue
            if knee is None:
                log(f"WARNING: Motor knee_motor_{side}{idx} not found")
                continue

            # Use position control (stable for articulated legs).
            hip.setVelocity(5.0)
            knee.setVelocity(5.0)
            hip.setPosition(HIP_SIGN[leg_id] * HIP_STAND)
            knee.setPosition(KNEE_STANCE_POS)

            self.hips[leg_id] = hip
            self.knees[leg_id] = knee

        self.walk_start_time = None
        self.is_walking = False

        # State machine
        self.state = STATE_IDLE
        self.previous_state = None
        self.step_count = 0
        self.battery_print_counter = 0

        # Delivery tracking
        self.delivery_queue = []
        self.current_target_index = 0
        self.delivered_houses = set()
        self.deliveries_completed = 0
        self.deliver_timer = 0
        self.avoid_cooldown = 0
        self.prev_target_distance = None
        self.no_progress_steps = 0
        self.boundary_recovery_steps = 0
        self.boundary_reverse_steps = 0

        # Supervisor API access for DEF nodes in world.
        self.supervisor = self.robot
        self.boxes = {}
        self.load_boxes()
        self.payload_node = None
        self.payload_translation = None
        self.payload_attached = False
        self.payload_home_pos = None
        self.drop_zone_pos = None
        self.current_run_with_payload = True
        self.calibrate_world_frame()
        self.load_payload_nodes()
        self.place_payload_near_robot()

        log("Robot initialized successfully")
        self.print_help()

    def calibrate_world_frame(self):
        """
        Recenter waypoints to robot spawn when world coordinates are offset.
        This keeps HOME/houses near the robot even if the map is translated.
        """
        try:
            sx, sy = self.navigation.get_position()
        except:
            return

        hx, hy = WAYPOINTS["HOME"]
        offset_x = sx - hx
        offset_y = sy - hy

        # Only shift when map is clearly offset from configured waypoint frame.
        if math.sqrt(offset_x * offset_x + offset_y * offset_y) > 5.0:
            for name in list(WAYPOINTS.keys()):
                wx, wy = WAYPOINTS[name]
                WAYPOINTS[name] = (wx + offset_x, wy + offset_y)

            for name in list(BOX_ORIGINS.keys()):
                bx, by, bz = BOX_ORIGINS[name]
                BOX_ORIGINS[name] = (bx + offset_x, by + offset_y, bz)

            log(f"Calibrated world frame by offset ({offset_x:.2f}, {offset_y:.2f})")

        # Use arena size from world (RectangleArena 50x50) around HOME.
        half_span = 24.0
        self.arena_min_x = WAYPOINTS["HOME"][0] - half_span
        self.arena_max_x = WAYPOINTS["HOME"][0] + half_span
        self.arena_min_z = WAYPOINTS["HOME"][1] - half_span
        self.arena_max_z = WAYPOINTS["HOME"][1] + half_span

    def load_boxes(self):
        """Load box nodes from world for delivery visualization"""
        box_names = ["BOX_A", "BOX_B", "BOX_C", "BOX_D"]
        for box_name in box_names:
            try:
                box_node = self.supervisor.getFromDef(box_name)
                if box_node:
                    self.boxes[box_name] = box_node
                    log(f"Loaded box: {box_name}")
            except:
                log(f"WARNING: Could not load box {box_name} (robot may not be Supervisor type)")

    def load_payload_nodes(self):
        """Load optional world payload nodes for visible pickup/drop presentation."""
        try:
            self.payload_node = self.supervisor.getFromDef("DELIVERY_BLOCK")
            if self.payload_node:
                self.payload_translation = self.payload_node.getField("translation")
                pos = self.payload_translation.getSFVec3f()
                self.payload_home_pos = [pos[0], pos[1], pos[2]]
                log("Loaded payload node: DELIVERY_BLOCK")
        except:
            self.payload_node = None
            self.payload_translation = None

        try:
            drop_node = self.supervisor.getFromDef("DELIVERY_DROP_ZONE")
            if drop_node:
                drop_pos = drop_node.getField("translation").getSFVec3f()
                self.drop_zone_pos = [drop_pos[0], drop_pos[1], drop_pos[2]]
                log("Loaded drop zone: DELIVERY_DROP_ZONE")
        except:
            self.drop_zone_pos = None

    def reset_payload(self):
        """Put payload back to its original world location for a new run."""
        self.payload_attached = False
        if self.payload_translation and self.payload_home_pos:
            self.payload_translation.setSFVec3f(list(self.payload_home_pos))

    def hide_payload(self):
        """Hide payload from scene for navigation-only runs."""
        self.payload_attached = False
        if self.payload_translation:
            self.payload_translation.setSFVec3f([0.0, -5.0, 0.0])

    def attach_payload(self):
        """Attach payload to robot for visible carrying."""
        if self.payload_translation is None:
            return
        self.payload_attached = True
        self.update_payload_pose()
        log("Package collected and loaded on robot")

    def place_payload_near_robot(self):
        """Place payload on ground near current robot pose before pickup."""
        if self.payload_translation is None:
            return

        # Use supervisor translation for deterministic placement even before
        # GPS/compass values stabilize.
        try:
            robot_node = self.supervisor.getSelf()
            robot_pos = robot_node.getField("translation").getSFVec3f()
            x = robot_pos[0]
            z = robot_pos[1]
        except:
            x, z = self.navigation.get_position()

        # Tiny fixed world offset so spawn is always visually near.
        px = x + PICKUP_SIDE
        py = z + PICKUP_AHEAD
        self.payload_translation.setSFVec3f([px, py, PAYLOAD_GROUND_Y])

    def drop_payload_at(self, x, z):
        """Drop payload to a world location."""
        if self.payload_translation is None:
            return
        self.payload_translation.setSFVec3f([x, z, PAYLOAD_GROUND_Y])
        self.payload_attached = False

    def update_payload_pose(self):
        """Update carried payload position so it follows robot body."""
        if not self.payload_attached or self.payload_translation is None:
            return

        # Use supervisor pose so payload follows robot deterministically.
        try:
            robot_node = self.supervisor.getSelf()
            robot_pos = robot_node.getField("translation").getSFVec3f()
            x = robot_pos[0]
            y = robot_pos[1]
        except:
            x, y = self.navigation.get_position()

        px = x
        py = y + CARRY_AHEAD
        self.payload_translation.setSFVec3f([px, py, CARRY_HEIGHT])

    def hide_box(self, house_name):
        """Hide delivery box by moving it below world"""
        box_map = {"HOUSE_A": "BOX_A", "HOUSE_B": "BOX_B", "HOUSE_C": "BOX_C", "HOUSE_D": "BOX_D"}
        box_name = box_map.get(house_name)
        
        if box_name in self.boxes:
            try:
                trans_field = self.boxes[box_name].getField("translation")
                trans_field.setSFVec3f([0, -5, 0])
                log(f"Package collected at {house_name}")
            except:
                pass

    def restore_boxes(self):
        """Restore all boxes to original positions for new cycle"""
        for house in ["HOUSE_A", "HOUSE_B", "HOUSE_C", "HOUSE_D"]:
            box_map = {"HOUSE_A": "BOX_A", "HOUSE_B": "BOX_B", "HOUSE_C": "BOX_C", "HOUSE_D": "BOX_D"}
            box_name = box_map.get(house)
            
            if box_name in self.boxes and box_name in BOX_ORIGINS:
                try:
                    trans_field = self.boxes[box_name].getField("translation")
                    orig_pos = BOX_ORIGINS[box_name]
                    trans_field.setSFVec3f(list(orig_pos))
                except:
                    pass

    def print_help(self):
        """Print control help menu"""
        log("=== DELIVERY ROBOT CONTROLS ===")
        log("S - Start delivery to ALL houses")
        log("N - Navigate ALL houses (no payload)")
        log("A - Deliver to HOUSE_A only")
        log("B - Deliver to HOUSE_B only")
        log("C - Deliver to HOUSE_C only")
        log("D - Deliver to HOUSE_D only")
        log("G - Grab/Release payload manually")
        log("Q - Stop and return to HOME")
        log("P - Print status report")
        log("================================")

    def optimize_route(self, houses_list):
        """
        Nearest-neighbor path optimization
        Returns ordered list of houses to visit
        """
        if not houses_list:
            return []

        unvisited = set(houses_list)
        current_pos = WAYPOINTS["HOME"]
        result = []

        while unvisited:
            # Find nearest unvisited house
            nearest_house = min(
                unvisited,
                key=lambda h: math.sqrt(
                    (WAYPOINTS[h][0] - current_pos[0])**2 +
                    (WAYPOINTS[h][1] - current_pos[1])**2
                )
            )
            result.append(nearest_house)
            current_pos = WAYPOINTS[nearest_house]
            unvisited.remove(nearest_house)

        return result

    def start_delivery(self, houses_list, with_payload=True):
        """Start route to specified houses, optionally with visible payload delivery."""
        if self.state != STATE_IDLE:
            log(f"Start command ignored while state={self.state}")
            return

        if not houses_list:
            log("No houses selected for delivery")
            return

        self.current_run_with_payload = with_payload
        self.delivered_houses.clear()
        self.restore_boxes()

        if self.current_run_with_payload:
            self.place_payload_near_robot()
            self.attach_payload()
        else:
            self.hide_payload()
        
        # Optimize route
        optimized = self.optimize_route(houses_list)
        self.delivery_queue = optimized + ["HOME"]
        self.current_target_index = 0

        mode_label = "DELIVERY" if self.current_run_with_payload else "NAVIGATION-ONLY"
        log(f"Route planned ({mode_label}): HOME → {' → '.join(optimized)} → HOME")
        self.transition_to(STATE_NAVIGATING)

    def handle_keyboard(self):
        """Process keyboard input"""
        if not self.keyboard:
            return

        key = self.keyboard.getKey()
        if key == -1:
            return

        # S - all houses
        if key == ord('S'):
            self.start_delivery(["HOUSE_A", "HOUSE_B", "HOUSE_C", "HOUSE_D"], with_payload=True)

        # N - all houses navigation only (no payload)
        elif key == ord('N'):
            self.start_delivery(["HOUSE_A", "HOUSE_B", "HOUSE_C", "HOUSE_D"], with_payload=False)

        # Individual houses
        elif key == ord('A'):
            self.start_delivery(["HOUSE_A"], with_payload=True)
        elif key == ord('B'):
            self.start_delivery(["HOUSE_B"], with_payload=True)
        elif key == ord('C'):
            self.start_delivery(["HOUSE_C"], with_payload=True)
        elif key == ord('D'):
            self.start_delivery(["HOUSE_D"], with_payload=True)

        # G - manual payload grab/release for presentation demos
        elif key == ord('G'):
            if self.payload_attached:
                x, z = self.navigation.get_position()
                self.drop_payload_at(x, z)
                log("Payload released")
            else:
                self.place_payload_near_robot()
                self.attach_payload()

        # Q - stop and return
        elif key == ord('Q'):
            if self.state != STATE_IDLE:
                log("STOP command received - returning to HOME")
                self.delivery_queue = ["HOME"]
                self.current_target_index = 0
                self.transition_to(STATE_RETURNING)

        # P - print status
        elif key == ord('P'):
            self.print_status()

    def transition_to(self, new_state):
        """Transition to a new state with logging"""
        if new_state != self.state:
            old_state = self.state
            self.state = new_state
            
            # Get target info for log
            target_info = ""
            if self.state == STATE_NAVIGATING or self.state == STATE_DELIVERING:
                if self.current_target_index < len(self.delivery_queue):
                    target_info = f" ({self.delivery_queue[self.current_target_index]})"

            log(f"STATE: {old_state} → {new_state}{target_info}")

    def boundary_turn_direction(self, current_pos):
        """Return preferred turn direction when near boundary: -1 left, 1 right."""
        heading = self.navigation.get_heading()
        center_bearing = self.navigation.get_bearing(current_pos, WAYPOINTS["HOME"])
        error_to_center = self.navigation.normalize_angle(center_bearing - heading)
        return -1 if error_to_center > 0.0 else 1

    def is_near_boundary(self, current_pos):
        """Detect whether robot is too close to arena edge."""
        x, z = current_pos
        return (
            x <= (self.arena_min_x + BOUNDARY_MARGIN)
            or x >= (self.arena_max_x - BOUNDARY_MARGIN)
            or z <= (self.arena_min_z + BOUNDARY_MARGIN)
            or z >= (self.arena_max_z - BOUNDARY_MARGIN)
        )

    def boundary_avoidance_needed(self, current_pos):
        """Trigger boundary avoidance only when near edge and heading outward."""
        x, z = current_pos
        nx = 0.0
        nz = 0.0

        if x <= (self.arena_min_x + BOUNDARY_MARGIN):
            nx += -1.0
        if x >= (self.arena_max_x - BOUNDARY_MARGIN):
            nx += 1.0
        if z <= (self.arena_min_z + BOUNDARY_MARGIN):
            nz += -1.0
        if z >= (self.arena_max_z - BOUNDARY_MARGIN):
            nz += 1.0

        # Not near boundary.
        if nx == 0.0 and nz == 0.0:
            return False

        # Normalize outward normal at corners.
        mag = math.sqrt(nx * nx + nz * nz)
        nx /= mag
        nz /= mag

        heading = self.navigation.get_heading()
        # Heading vector in world x/z.
        hx = math.sin(heading)
        hz = math.cos(heading)
        outward_dot = hx * nx + hz * nz

        return outward_dot > BOUNDARY_OUTWARD_DOT

    def update_fsm(self):
        """Update finite state machine"""
        current_pos = self.navigation.get_position()

        if self.state == STATE_IDLE:
            # Wait for keyboard command
            pass

        elif self.state == STATE_NAVIGATING:
            target_name = self.delivery_queue[self.current_target_index]
            target_pos = WAYPOINTS[target_name]

            near_boundary = self.is_near_boundary(current_pos)

            # Boundary recovery: keep NAVIGATING but force inward steering for a while.
            if near_boundary:
                self.boundary_recovery_steps = max(self.boundary_recovery_steps, BOUNDARY_RECOVERY_STEPS)
                self.boundary_reverse_steps = max(self.boundary_reverse_steps, BOUNDARY_REVERSE_STEPS)

            # Check if we should avoid obstacle (disabled while near boundary to prevent oscillation).
            if self.boundary_recovery_steps == 0 and (not near_boundary) and self.avoid_cooldown == 0 and self.obstacle_detector.is_blocked():
                self.obstacle_detector.start_avoidance()
                self.stop_motors()
                self.transition_to(STATE_AVOIDING)
                return
            elif near_boundary:
                # Drop stale blocked counts while boundary-recovering.
                self.obstacle_detector.blocked_count = 0

            # Fallback: if robot is not making progress, force avoidance to escape contact.
            # Disable this while boundary recovery is active to avoid NAVIGATING<->AVOIDING thrash at edges.
            dx = target_pos[0] - current_pos[0]
            dz = target_pos[1] - current_pos[1]
            current_distance = math.sqrt(dx**2 + dz**2)

            if near_boundary or self.boundary_recovery_steps > 0 or self.boundary_reverse_steps > 0:
                self.no_progress_steps = 0
            else:
                if self.prev_target_distance is not None:
                    if current_distance < (self.prev_target_distance - STUCK_PROGRESS_EPS):
                        self.no_progress_steps = 0
                    else:
                        self.no_progress_steps += 1

                    if self.no_progress_steps >= STUCK_STEPS_TRIGGER:
                        self.obstacle_detector.start_avoidance()
                        self.stop_motors()
                        self.no_progress_steps = 0
                        self.transition_to(STATE_AVOIDING)
                        return

            self.prev_target_distance = current_distance

            if self.navigation.has_arrived(current_pos, target_pos):
                self.prev_target_distance = None
                self.no_progress_steps = 0
                if target_name == "HOME":
                    self.transition_to(STATE_CHARGING)
                else:
                    self.transition_to(STATE_DELIVERING)

        elif self.state == STATE_AVOIDING:
            # Update obstacle avoidance
            should_continue, avoid_speeds = self.obstacle_detector.update_avoidance()

            if not should_continue:
                # Obstacle cleared, resume navigation
                self.avoid_cooldown = 70
                self.boundary_recovery_steps = BOUNDARY_RECOVERY_STEPS
                self.transition_to(STATE_NAVIGATING)
            else:
                # Still avoiding, set speeds and return
                self.set_motor_speeds(avoid_speeds[0], avoid_speeds[1])
                return

        elif self.state == STATE_DELIVERING:
            # Stop and wait 3 seconds
            self.deliver_timer += 1

            if self.deliver_timer >= DELIVER_DURATION:
                # Delivery complete
                target_name = self.delivery_queue[self.current_target_index]
                if self.current_run_with_payload:
                    log(f"Delivered to {target_name}")
                    self.hide_box(target_name)
                    self.delivered_houses.add(target_name)
                else:
                    log(f"Reached waypoint {target_name} (navigation-only)")

                # Visible payload drop for presentation demo.
                if self.current_run_with_payload and self.payload_attached:
                    target = WAYPOINTS.get(target_name, (current_pos[0], current_pos[1]))
                    self.drop_payload_at(target[0], target[1])
                    log(f"Dropped package at {target_name}")

                # Move to next target
                self.current_target_index += 1
                self.deliver_timer = 0

                if self.current_target_index >= len(self.delivery_queue):
                    # All deliveries done, return to HOME
                    self.delivery_queue = ["HOME"]
                    self.current_target_index = 0

                self.transition_to(STATE_NAVIGATING)

        elif self.state == STATE_RETURNING:
            # Navigate back to HOME
            if self.is_near_boundary(current_pos):
                self.boundary_recovery_steps = max(self.boundary_recovery_steps, BOUNDARY_RECOVERY_STEPS)

            home_pos = WAYPOINTS["HOME"]
            if self.navigation.has_arrived(current_pos, home_pos):
                self.transition_to(STATE_CHARGING)

        elif self.state == STATE_CHARGING:
            # Recharge at HOME
            if self.battery_manager.is_full():
                self.deliveries_completed += 1
                log(f"Cycle complete! Deliveries done: {self.deliveries_completed}, Battery: {self.battery_manager.level:.1f}%")
                self.transition_to(STATE_IDLE)

    def set_motor_speeds(self, left_speed, right_speed):
        """
        Drive robot using a stable position-based tripod gait.
        left_speed/right_speed are interpreted as differential steering commands.
        """
        if len(self.hips) < 6 or len(self.knees) < 6:
            return

        left_speed = self.clamp_speed(left_speed)
        right_speed = self.clamp_speed(right_speed)

        forward = max(-1.0, min(1.0, (left_speed + right_speed) / (2.0 * MAX_SPEED)))
        turn = max(-1.0, min(1.0, (right_speed - left_speed) / (2.0 * MAX_SPEED)))

        # Stand still when command is near zero.
        if abs(forward) < 0.05 and abs(turn) < 0.05:
            self.is_walking = False
            self.walk_start_time = None
            self.stop_motors()
            return

        # Start walk timing on the first active command.
        if not self.is_walking:
            self.is_walking = True
            self.walk_start_time = self.robot.getTime()

        elapsed = self.robot.getTime() - self.walk_start_time
        phase_global = (elapsed % GAIT_PERIOD) / GAIT_PERIOD
        ramp = min(elapsed / RAMP_TIME, 1.0)

        drive_scale = max(0.35, abs(forward))
        drive_sign = 1.0 if forward >= 0.0 else -1.0
        steer_scale = max(-1.0, min(1.0, turn))

        for leg in LEG_IDS:
            phase = (phase_global + PHASE_OFFSET[leg]) % 1.0

            if phase < STANCE_RATIO:
                u = phase / STANCE_RATIO
                hip_mag = drive_sign * drive_scale * (HIP_FORWARD - (HIP_FORWARD + HIP_BACK) * u)
                knee = KNEE_STANCE_POS
            else:
                u = (phase - STANCE_RATIO) / (1.0 - STANCE_RATIO)
                hip_mag = drive_sign * drive_scale * (-HIP_BACK + (HIP_FORWARD + HIP_BACK) * u)
                knee = KNEE_STANCE_POS + ( -0.012 - KNEE_STANCE_POS) * math.sin(math.pi * u)

            # Differential steering bias. For near-zero forward commands, bias more
            # aggressively so obstacle-avoid turns can break contact.
            turn_gain = 0.45 if abs(forward) < 0.20 else 0.25
            if leg.startswith("l"):
                hip_mag *= max(0.45, 1.0 - turn_gain * steer_scale)
            else:
                hip_mag *= max(0.45, 1.0 + turn_gain * steer_scale)

            hip_target = HIP_SIGN[leg] * (HIP_STAND + ramp * hip_mag)

            self.hips[leg].setPosition(max(-0.7, min(0.7, hip_target)))
            knee = max(KNEE_MIN_POS, min(KNEE_MAX_POS, knee))
            self.knees[leg].setPosition(knee)

    def clamp_speed(self, speed):
        """Clamp velocity command to motor-safe range."""
        return max(-MOTOR_MAX_CMD, min(MOTOR_MAX_CMD, speed))

    def stop_motors(self):
        """Return all legs to a stable standing pose."""
        self.is_walking = False
        self.walk_start_time = None
        for leg in LEG_IDS:
            if leg in self.hips:
                self.hips[leg].setPosition(HIP_SIGN[leg] * HIP_STAND)
            if leg in self.knees:
                self.knees[leg].setPosition(max(KNEE_MIN_POS, min(KNEE_MAX_POS, KNEE_STANCE_POS)))

    def print_status(self):
        """Print detailed status report"""
        current_pos = self.navigation.get_position()
        target_name = self.delivery_queue[self.current_target_index] if self.current_target_index < len(self.delivery_queue) else "None"
        
        log("=" * 60)
        log("STATUS REPORT")
        log(f"State: {self.state}")
        log(f"Run Mode: {'DELIVERY' if self.current_run_with_payload else 'NAVIGATION-ONLY'}")
        log(f"Battery: {self.battery_manager.level:.1f}%")
        log(f"Position: ({current_pos[0]:.2f}, {current_pos[1]:.2f})")
        log(f"Current Target: {target_name}")
        log(f"Delivered Houses: {', '.join(sorted(self.delivered_houses)) if self.delivered_houses else 'None'}")
        log(f"Payload Attached: {'Yes' if self.payload_attached else 'No'}")
        log(f"Cycles Completed: {self.deliveries_completed}")
        log(f"Queue: {' → '.join(self.delivery_queue)}")
        log("=" * 60)

    def run(self):
        """Main control loop"""
        log("Starting main control loop...")

        while self.robot.step(TIME_STEP) != -1:
            self.step_count += 1

            if self.avoid_cooldown > 0:
                self.avoid_cooldown -= 1

            # ===== FIXED ORDER EVERY STEP =====
            # 1. Update battery
            self.battery_manager.update(self.state)

            # 2. Handle keyboard input
            self.handle_keyboard()

            # 3. Update sensor readings
            self.obstacle_detector.update_readings()

            # 4. Update FSM
            self.update_fsm()

            # 5. Set motors based on current state
            if self.state == STATE_IDLE or self.state == STATE_CHARGING or self.state == STATE_DELIVERING:
                self.stop_motors()

            elif self.state == STATE_NAVIGATING:
                current_pos = self.navigation.get_position()
                heading = self.navigation.get_heading()
                near_boundary = self.is_near_boundary(current_pos)

                # Immediate brake path: stop before contact, then enter avoidance.
                if self.avoid_cooldown == 0 and self.obstacle_detector.should_brake_now():
                    self.stop_motors()
                    if (
                        self.avoid_cooldown == 0
                        and self.boundary_recovery_steps == 0
                        and (not near_boundary)
                    ):
                        self.obstacle_detector.start_avoidance()
                        self.transition_to(STATE_AVOIDING)
                    continue

                # First, back off from boundary for a short time.
                if self.boundary_reverse_steps > 0:
                    self.boundary_reverse_steps -= 1
                    self.set_motor_speeds(-0.85 * MAX_SPEED, -0.85 * MAX_SPEED)
                    continue

                # After avoidance near boundary, briefly steer toward HOME to move inward.
                if self.boundary_recovery_steps > 0:
                    target_pos = WAYPOINTS["HOME"]
                    self.boundary_recovery_steps -= 1
                else:
                    target_name = self.delivery_queue[self.current_target_index]
                    target_pos = WAYPOINTS[target_name]

                left_speed, right_speed = self.navigation.calculate_steering(current_pos, heading, target_pos)
                self.set_motor_speeds(left_speed, right_speed)

            elif self.state == STATE_AVOIDING:
                # Already handled in update_fsm()
                pass

            elif self.state == STATE_RETURNING:
                current_pos = self.navigation.get_position()
                heading = self.navigation.get_heading()
                home_pos = WAYPOINTS["HOME"]

                left_speed, right_speed = self.navigation.calculate_steering(current_pos, heading, home_pos)
                self.set_motor_speeds(left_speed, right_speed)

            # 6. Low battery check (every step)
            if self.battery_manager.is_low() and self.state not in [STATE_RETURNING, STATE_CHARGING]:
                log(f"LOW BATTERY ({self.battery_manager.level:.1f}%) - Auto-returning to HOME")
                self.delivery_queue = ["HOME"]
                self.current_target_index = 0
                self.transition_to(STATE_RETURNING)

            # 7. Update mini-map
            if self.state != STATE_IDLE:
                current_pos = self.navigation.get_position()
                heading = self.navigation.get_heading()
                self.minimap.update(current_pos, heading, self.delivered_houses)

            # 7a. Delivery safeguard: keep payload attached while heading to first drop.
            if (
                self.current_run_with_payload
                and not self.payload_attached
                and len(self.delivered_houses) == 0
                and self.state in [STATE_NAVIGATING, STATE_AVOIDING, STATE_RETURNING]
            ):
                self.attach_payload()

            # 7b. Keep payload attached to robot while carrying.
            self.update_payload_pose()

            # 8. Print battery periodically
            self.battery_print_counter += 1
            if self.battery_print_counter >= BATTERY_PRINT_STEPS:
                log(f"Battery: {self.battery_manager.level:.1f}%")
                self.battery_print_counter = 0


# ===== ENTRY POINT =====
if __name__ == "__main__":
    robot = DeliveryRobot()
    robot.run()
