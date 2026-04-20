"""
MAIN HEXAPOD AUTONOMOUS DELIVERY ROBOT CONTROLLER
Integrates gait, navigation, delivery, and UI systems
"""

from controller import Supervisor
import math

# Files are in same directory - no path adjustment needed
from delivery_system import DeliverySystem, DELIVERY_POINTS, WAYPOINT_TOLERANCE
from ui_control import SimulationInterface, print_control_help

# ========== GAIT PARAMETERS ==========
TIMESTEP = 8
GAIT_FREQ = 1.2
HIP_FRONT_STAND = 0.08            # Front legs at natural stable angle (~4.6°)
HIP_REAR_STAND = 0.08             # Rear legs at natural stable angle  
KNEE_STAND = 0.0                  # Neutral knee position (no compression)
HIP_FORWARD_EXT = 0.58            # Forward reach: ±0.58 rad (total 1.16 rad stride, safe within ±0.7)
HIP_BACK_EXT = 0.58               # Backward push: ±0.58 rad for symmetric gait
KNEE_LIFT = 0.012                 # Lift to 1.2cm for better step definition
RAMP_TIME = 1.5
SETTLE_TIME = 2.0                 # Extra time for ground contact stabilization
HEADING_P_GAIN = 3.0              # Increased to 3.0 for more aggressive steering (was 2.0)

HIP_NAMES = [
    "hip_motor_l0", "hip_motor_l1", "hip_motor_l2",
    "hip_motor_r0", "hip_motor_r1", "hip_motor_r2",
]

KNEE_NAMES = [
    "knee_motor_l0", "knee_motor_l1", "knee_motor_l2",
    "knee_motor_r0", "knee_motor_r1", "knee_motor_r2",
]

TRIPOD_A = ["l0", "r1", "l2"]
TRIPOD_B = ["r0", "l1", "r2"]

HIP_SIGN = {
    "l0": 1.0, "l1": 1.0, "l2": 1.0,
    "r0": -1.0, "r1": -1.0, "r2": -1.0,
}

class HexapodAutonomousDelivery:
    def __init__(self):
        self.robot = Supervisor()
        self.timestep = int(self.robot.getBasicTimeStep())
        
        print("\n" + "="*70)
        print("  HEXAPOD AUTONOMOUS DELIVERY SYSTEM INITIALIZING")
        print("="*70)
        
        # Initialize delivery system with shared robot instance
        self.delivery = DeliverySystem(self.robot)
        
        # Initialize UI
        self.ui = SimulationInterface(self.robot, self.delivery)
        print_control_help()
        
        # Motor initialization
        self.hips = {}
        self.knees = {}
        self.hip_sensors = {}
        self.knee_sensors = {}
        
        print("[INIT] Setting up motors and sensors...")
        for i, (hip_name, knee_name) in enumerate(zip(HIP_NAMES, KNEE_NAMES)):
            leg_id = ["l0", "l1", "l2", "r0", "r1", "r2"][i]
            
            try:
                hip = self.robot.getDevice(hip_name)
                knee = self.robot.getDevice(knee_name)
                
                # Check if devices were found
                if hip is None or knee is None:
                    print(f"[WARNING] Motor not found for {leg_id}")
                    continue
                
                hip_sensor = self.robot.getDevice(hip_name.replace("motor", "sensor"))
                knee_sensor = self.robot.getDevice(knee_name.replace("motor", "sensor"))
                
                hip.setVelocity(2.0)
                knee.setVelocity(2.0)
                hip.setAvailableTorque(10.0)  # Match Webots motor maxTorque
                knee.setAvailableTorque(10.0)
                
                # Only enable sensors if they exist
                if hip_sensor is not None:
                    hip_sensor.enable(self.timestep)
                if knee_sensor is not None:
                    knee_sensor.enable(self.timestep)
                
                self.hips[leg_id] = hip
                self.knees[leg_id] = knee
                self.hip_sensors[leg_id] = hip_sensor if hip_sensor else None
                self.knee_sensors[leg_id] = knee_sensor if knee_sensor else None
                
                print(f"[MOTOR] Initialized {leg_id}")
            except Exception as e:
                print(f"[ERROR] Failed to initialize {leg_id}: {e}")
        
        # IMU for balance
        self.imu = None
        try:
            self.imu = self.robot.getDevice("imu")
            if self.imu is not None:
                self.imu.enable(self.timestep)
                print("[INIT] IMU initialized")
        except:
            print("[WARNING] IMU not found or failed to initialize")
        
        self.legs = ["l0", "l1", "l2", "r0", "r1", "r2"]
        self.walk_start_time = 0.0
        self.walk_timer = 0.0
        self.is_walking = False
        self.direction_sign = 1.0
        self.current_heading = 0.0  # Robot's current heading (radians)
        self.last_status_time = 0.0
        
        print("[INIT] Hexapod systems ready!")
        
    def clamp(self, v, lo, hi):
        """Clamp value between bounds"""
        return max(lo, min(hi, v))
    
    def hip_cmd(self, leg, angle_mag):
        """Generate hip command with direction"""
        return self.clamp(HIP_SIGN[leg] * self.direction_sign * angle_mag, -0.7, 0.7)
    
    def hip_stand_mag(self, leg):
        """Get standing hip magnitude based on leg position"""
        return HIP_FRONT_STAND if leg in ("l0", "r0") else HIP_REAR_STAND
    
    def apply_stand_pose(self):
        """Apply standing pose - stationary and stable (symmetric, no HIP_SIGN inversion)"""
        for leg in self.legs:
            if leg in self.hips and self.hips[leg] is not None:
                # Get standing hip magnitude directly without HIP_SIGN inversion
                # This ensures both left and right legs have symmetric standing pose
                stand_mag = self.hip_stand_mag(leg)
                # Clamp directly to motor range
                hip_target = self.clamp(stand_mag, -0.7, 0.7)
                self.hips[leg].setPosition(hip_target)
            if leg in self.knees and self.knees[leg] is not None:
                self.knees[leg].setPosition(self.clamp(KNEE_STAND, -0.02, 0.02))  # Knee slider range
    
    def apply_walk_gait(self, elapsed_time, ramp=1.0):
        """Apply alternating tripod walking gait"""
        # Skip if no motors available
        if not self.hips or not self.knees:
            return
            
        p = (elapsed_time * GAIT_FREQ) % 1.0
        
        if p < 0.5:
            swing_pair = TRIPOD_A
            stance_pair = TRIPOD_B
            u = p / 0.5
        else:
            swing_pair = TRIPOD_B
            stance_pair = TRIPOD_A
            u = (p - 0.5) / 0.5
        
        for leg in self.legs:
            if leg not in self.hips or self.hips[leg] is None:
                continue
            if leg not in self.knees or self.knees[leg] is None:
                continue
                
            if leg in swing_pair:
                # Swing phase: lift and move forward
                hip_target = (self.hip_stand_mag(leg) + 
                             (-HIP_BACK_EXT + (HIP_FORWARD_EXT + HIP_BACK_EXT) * u) * ramp)
                knee_target = KNEE_STAND - KNEE_LIFT * math.sin(math.pi * u) * ramp
            else:
                # Stance phase: push backward for propulsion
                hip_target = (self.hip_stand_mag(leg) + 
                             (HIP_FORWARD_EXT - (HIP_FORWARD_EXT + HIP_BACK_EXT) * u) * ramp)
                knee_target = KNEE_STAND
            
            self.hips[leg].setPosition(self.clamp(self.hip_cmd(leg, hip_target), -0.8, 0.8))
            self.knees[leg].setPosition(self.clamp(knee_target, -0.02, 0.02))  # Knee slider range
    
    def update_gait_control(self, current_time):
        """Determine if robot should walk based on delivery state"""
        
        # Check if we should be moving
        should_move = False
        
        if self.delivery.state == "NAVIGATING":
            current_pos = self.delivery.get_robot_position()
            target_pos = DELIVERY_POINTS[self.delivery.current_target]
            distance = math.sqrt((current_pos[0] - target_pos[0])**2 + 
                               (current_pos[1] - target_pos[1])**2)
            
            # Calculate target heading to navigate toward goal
            dx = target_pos[0] - current_pos[0]
            dz = target_pos[1] - current_pos[1]
            target_heading = math.atan2(dx, dz)  # Angle to target
            
            # Update heading based on error
            heading_error = target_heading - self.current_heading
            # Normalize to [-pi, pi]
            while heading_error > math.pi:
                heading_error -= 2 * math.pi
            while heading_error < -math.pi:
                heading_error += 2 * math.pi
            
            # Apply proportional control: positive error = turn right
            self.direction_sign = self.clamp(1.0 + HEADING_P_GAIN * heading_error / math.pi, -1.0, 1.0)
            
            # Start walking if far from target and no obstacle
            if (distance > WAYPOINT_TOLERANCE and 
                not self.delivery.should_avoid_obstacle() and 
                self.delivery.battery_level > 5):
                should_move = True
        
        elif self.delivery.state == "RETURNING":
            current_pos = self.delivery.get_robot_position()
            home_pos = DELIVERY_POINTS["HOME"]
            distance = math.sqrt((current_pos[0] - home_pos[0])**2 + 
                               (current_pos[1] - home_pos[1])**2)
            
            # Calculate target heading to navigate home
            dx = home_pos[0] - current_pos[0]
            dz = home_pos[1] - current_pos[1]
            target_heading = math.atan2(dx, dz)
            
            # Update heading based on error
            heading_error = target_heading - self.current_heading
            # Normalize to [-pi, pi]
            while heading_error > math.pi:
                heading_error -= 2 * math.pi
            while heading_error < -math.pi:
                heading_error += 2 * math.pi
            
            # Apply proportional control
            self.direction_sign = self.clamp(1.0 + HEADING_P_GAIN * heading_error / math.pi, -1.0, 1.0)
            
            if (distance > WAYPOINT_TOLERANCE and 
                not self.delivery.should_avoid_obstacle() and 
                self.delivery.battery_level > 5):
                should_move = True
        
        # Update walking state
        if should_move and not self.is_walking:
            self.is_walking = True
            self.walk_start_time = current_time
        elif not should_move:
            self.is_walking = False
        
        # Apply gait
        if self.is_walking:
            elapsed = current_time - self.walk_start_time
            ramp = self.clamp(elapsed / RAMP_TIME, 0.0, 1.0)
            self.apply_walk_gait(elapsed, ramp)
        else:
            self.apply_stand_pose()
    
    def run_initialization(self):
        """Initialize robot to standing position"""
        print("\n[STARTUP] Standing up and settling...")
        
        for i in range(int(SETTLE_TIME / (self.timestep / 1000))):
            self.robot.step(self.timestep)
            self.apply_stand_pose()
        
        print("[STARTUP] Ready! Awaiting delivery commands...")
        print("[STARTUP] Press 'S' to start all deliveries, or 'A'/'B'/'C'/'D' for specific house\n")
    
    def run(self):
        """Main control loop"""
        self.run_initialization()
        
        status_interval = 3.0  # Print status every 3 seconds
        
        try:
            while self.robot.step(self.timestep) != -1:
                current_time = self.robot.getTime()
                
                # Handle keyboard input
                self.ui.handle_keyboard_input()
                
                # Update delivery system
                self.delivery.update()
                
                # Update current heading based on walking direction and gait progress
                # The heading changes proportionally to direction_sign
                if self.is_walking and self.direction_sign != 0:
                    # Update heading based on the gait phase and direction
                    heading_change_rate = 0.5 * self.direction_sign  # rad/s * direction
                    self.current_heading += heading_change_rate * (self.timestep / 1000.0)
                    # Normalize to [-pi, pi]
                    while self.current_heading > math.pi:
                        self.current_heading -= 2 * math.pi
                    while self.current_heading < -math.pi:
                        self.current_heading += 2 * math.pi
                
                # Update robot gait based on delivery state
                self.update_gait_control(current_time)
                
                # Render UI
                self.ui.render_ui()
                
                # Print status periodically
                if current_time - self.last_status_time > status_interval:
                    # Compact status line
                    pos = self.delivery.get_robot_position()
                    if self.delivery.current_target:
                        target_pos = DELIVERY_POINTS[self.delivery.current_target]
                        dist_to_target = math.sqrt((pos[0] - target_pos[0])**2 + 
                                                 (pos[1] - target_pos[1])**2)
                    else:
                        dist_to_target = 0
                    
                    print(f"[{current_time:6.1f}s] State: {self.delivery.state:11s} | "
                          f"Pos: ({pos[0]:6.2f}, {pos[1]:6.2f}) | "
                          f"Target: {self.delivery.current_target or 'NONE':10s} | "
                          f"Dist: {dist_to_target:5.2f}m | "
                          f"Battery: {self.delivery.battery_level:5.1f}% | "
                          f"Delivered: {self.delivery.delivered_count}")
                    
                    self.last_status_time = current_time
                
                # Check termination condition
                if self.delivery.state == "IDLE" and self.delivery.delivered_count > 0:
                    print("\n[COMPLETE] All deliveries finished! Awaiting next command...")
        
        except KeyboardInterrupt:
            print("\n[EXIT] Simulation terminated by user")
        except Exception as e:
            print(f"\n[ERROR] {e}")
            import traceback
            traceback.print_exc()

# ========== MAIN ==========
if __name__ == "__main__":
    robot = HexapodAutonomousDelivery()
    robot.run()
