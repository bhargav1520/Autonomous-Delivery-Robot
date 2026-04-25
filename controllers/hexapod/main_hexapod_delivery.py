"""
MAIN HEXAPOD AUTONOMOUS DELIVERY ROBOT CONTROLLER
Integrates gait, navigation, delivery, and UI systems
"""

from controller import Supervisor
import math
import sys
import os

# Add imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from delivery_system import DeliverySystem, DELIVERY_POINTS, WAYPOINT_TOLERANCE
from ui_control import SimulationInterface, print_control_help

# ========== GAIT PARAMETERS ==========
TIMESTEP = 8
GAIT_FREQ = 1.2
HIP_FRONT_STAND = 0.24
HIP_REAR_STAND = 0.20
KNEE_STAND = -1.00
HIP_FORWARD_EXT = 0.20
HIP_BACK_EXT = 0.22
KNEE_LIFT = 0.30
RAMP_TIME = 1.5
SETTLE_TIME = 1.0

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
        
        # Initialize delivery system with this robot instance
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
                hip_sensor = self.robot.getDevice(hip_name.replace("motor", "sensor"))
                knee_sensor = self.robot.getDevice(knee_name.replace("motor", "sensor"))
                
                hip.setVelocity(2.0)
                knee.setVelocity(2.0)
                hip.setAvailableTorque(15.0)
                knee.setAvailableTorque(15.0)
                
                hip_sensor.enable(self.timestep)
                knee_sensor.enable(self.timestep)
                
                self.hips[leg_id] = hip
                self.knees[leg_id] = knee
                self.hip_sensors[leg_id] = hip_sensor
                self.knee_sensors[leg_id] = knee_sensor
            except Exception as e:
                print(f"[ERROR] Failed to initialize {leg_id}: {e}")
        
        # IMU for balance
        self.imu = self.robot.getDevice("imu")
        self.imu.enable(self.timestep)
        
        self.legs = ["l0", "l1", "l2", "r0", "r1", "r2"]
        self.walk_start_time = 0.0
        self.walk_timer = 0.0
        self.is_walking = False
        self.direction_sign = 1.0
        self.last_status_time = 0.0
        self.last_obstacle_log = 0.0
        self.debug_obstacle = True  # Enable obstacle debug logging
        
        print("[INIT] Hexapod systems ready!")
        
    def clamp(self, v, lo, hi):
        """Clamp value between bounds"""
        return max(lo, min(hi, v))
    
    def hip_cmd(self, leg, angle_mag):
        """Generate hip command with direction"""
        return self.clamp(HIP_SIGN[leg] * self.direction_sign * angle_mag, -0.8, 0.8)
    
    def hip_stand_mag(self, leg):
        """Get standing hip magnitude based on leg position"""
        return HIP_FRONT_STAND if leg in ("l0", "r0") else HIP_REAR_STAND
    
    def apply_stand_pose(self):
        """Apply standing pose - stationary and stable"""
        for leg in self.legs:
            self.hips[leg].setPosition(self.hip_cmd(leg, self.hip_stand_mag(leg)))
            self.knees[leg].setPosition(self.clamp(KNEE_STAND, -1.5, 0.1))
    
    def apply_walk_gait(self, elapsed_time, ramp=1.0):
        """Apply alternating tripod walking gait"""
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
            self.knees[leg].setPosition(self.clamp(knee_target, -1.5, 0.1))
    
    def update_gait_control(self, current_time):
        """Determine if robot should walk based on delivery state with smart obstacle avoidance"""
        
        # Check if we should be moving
        should_move = False
        obstacle_detected = self.delivery.should_avoid_obstacle()
        escape_dir = self.delivery.get_obstacle_direction()
        clearances = self.delivery.get_clearances()
        
        # Debug: Log sensor readings periodically
        if self.debug_obstacle and (current_time - self.last_obstacle_log > 1.0):
            front_val = clearances.get('front', float('inf'))
            left_val = clearances.get('left', float('inf'))
            right_val = clearances.get('right', float('inf'))
            back_val = clearances.get('back', float('inf'))
            
            front_str = f"{front_val:.3f}m" if front_val < 10 else "∞"
            left_str = f"{left_val:.3f}m" if left_val < 10 else "∞"
            right_str = f"{right_val:.3f}m" if right_val < 10 else "∞"
            back_str = f"{back_val:.3f}m" if back_val < 10 else "∞"
            
            print(f"[DEBUG SENSORS @ {current_time:.1f}s] Front: {front_str} | Left: {left_str} | Right: {right_str} | Back: {back_str} | Obstacle: {obstacle_detected} | Escape: {escape_dir}")
            self.last_obstacle_log = current_time
        
        if self.delivery.state == "NAVIGATING":
            current_pos = self.delivery.get_robot_position()
            target_pos = DELIVERY_POINTS[self.delivery.current_target]
            distance = math.sqrt((current_pos[0] - target_pos[0])**2 + 
                               (current_pos[1] - target_pos[1])**2)
            
            # Handle obstacle avoidance with intelligent escape logic
            if obstacle_detected:
                print(f"[AVOID] Clearances - Front: {clearances['front']:.2f}m, Left: {clearances['left']:.2f}m, Right: {clearances['right']:.2f}m, Back: {clearances['back']:.2f}m")
                
                if escape_dir == 'FORWARD':
                    # Path ahead is clear, continue
                    self.direction_sign = 1.0
                    should_move = True
                    print(f"[AVOID] Path FORWARD is clear - proceeding")
                
                elif escape_dir == 'LEFT':
                    # Turn left to find opening
                    self.direction_sign = -1.0
                    should_move = True
                    print(f"[AVOID] Steering LEFT - found clear path")
                
                elif escape_dir == 'RIGHT':
                    # Turn right to find opening
                    self.direction_sign = 1.0
                    should_move = True
                    print(f"[AVOID] Steering RIGHT - found clear path")
                
                elif escape_dir == 'BACK':
                    # Move backward to create space
                    self.direction_sign = -1.0  # Reverse direction
                    should_move = True
                    print(f"[AVOID] Moving BACKWARD - creating space")
                
                elif escape_dir == 'BACK_HARD':
                    # Critical: obstacles very close, reverse urgently
                    self.direction_sign = -1.0
                    should_move = True
                    print(f"[AVOID] CRITICAL - Moving BACKWARD with urgency!")
                
                else:  # STOP
                    # Fully trapped, don't move
                    self.direction_sign = 1.0
                    should_move = False
                    print(f"[AVOID] BLOCKED - Cannot find escape route")
            
            else:
                # No obstacle, move toward target normally
                self.direction_sign = 1.0
                if (distance > WAYPOINT_TOLERANCE and 
                    self.delivery.battery_level > 5):
                    should_move = True
        
        elif self.delivery.state == "RETURNING":
            current_pos = self.delivery.get_robot_position()
            home_pos = DELIVERY_POINTS["HOME"]
            distance = math.sqrt((current_pos[0] - home_pos[0])**2 + 
                               (current_pos[1] - home_pos[1])**2)
            
            # Handle obstacle avoidance while returning
            if obstacle_detected:
                if escape_dir == 'FORWARD':
                    self.direction_sign = 1.0
                    should_move = True
                elif escape_dir == 'LEFT':
                    self.direction_sign = -1.0
                    should_move = True
                elif escape_dir == 'RIGHT':
                    self.direction_sign = 1.0
                    should_move = True
                elif escape_dir in ['BACK', 'BACK_HARD']:
                    self.direction_sign = -1.0
                    should_move = True
                    print(f"[RETURN] Reversing to avoid obstacle")
                else:
                    self.direction_sign = 1.0
                    should_move = False
            else:
                self.direction_sign = 1.0
                if (distance > WAYPOINT_TOLERANCE and 
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

