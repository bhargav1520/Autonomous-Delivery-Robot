"""
Hexapod Autonomous Delivery Robot Controller
Integrates gait control with delivery system navigation
"""

from controller import Supervisor
import math
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from delivery_system import DeliverySystem, DELIVERY_POINTS, WAYPOINT_TOLERANCE

# ========== GAIT CONFIGURATION ==========
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

PHASE_OFFSET = {
    "l0": 0.0, "r1": 0.0, "l2": 0.0,
    "r0": 0.5, "l1": 0.5, "r2": 0.5,
}

class HexapodDeliveryRobot:
    def __init__(self):
        self.robot = Supervisor()
        self.timestep = int(self.robot.getBasicTimeStep())
        
        # Initialize delivery system
        self.delivery = DeliverySystem()
        
        # Motor control
        self.hips = {}
        self.knees = {}
        self.hip_sensors = {}
        self.knee_sensors = {}
        
        for i, (hip_name, knee_name) in enumerate(zip(HIP_NAMES, KNEE_NAMES)):
            leg_id = ["l0", "l1", "l2", "r0", "r1", "r2"][i]
            
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
        
        # IMU for balance
        self.imu = self.robot.getDevice("imu")
        self.imu.enable(self.timestep)
        
        # Robot node
        try:
            self.robot_node = self.robot.getFromDef("HEXAPOD")
        except:
            self.robot_node = None
        
        self.legs = ["l0", "l1", "l2", "r0", "r1", "r2"]
        self.walk_start_time = 0.0
        self.last_print = 0.0
        self.direction_sign = 1.0
        self.direction_checked = False
        self.is_walking = False
        self.walk_timer = 0.0
        
        print("[HEXAPOD] Initialized")
        
    def clamp(self, v, lo, hi):
        return max(lo, min(hi, v))
    
    def hip_cmd(self, leg, angle_mag):
        return self.clamp(HIP_SIGN[leg] * self.direction_sign * angle_mag, -0.8, 0.8)
    
    def hip_stand_mag(self, leg):
        return HIP_FRONT_STAND if leg in ("l0", "r0") else HIP_REAR_STAND
    
    def apply_stand_pose(self):
        """Hold standing position"""
        for leg in self.legs:
            self.hips[leg].setPosition(self.hip_cmd(leg, self.hip_stand_mag(leg)))
            self.knees[leg].setPosition(self.clamp(KNEE_STAND, -1.5, 0.1))
    
    def apply_walk_gait(self, t, ramp=1.0):
        """Apply alternating tripod gait"""
        p = (t * GAIT_FREQ) % 1.0
        
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
                hip_target = self.hip_stand_mag(leg) + (-HIP_BACK_EXT + (HIP_FORWARD_EXT + HIP_BACK_EXT) * u) * ramp
                knee_target = KNEE_STAND - KNEE_LIFT * math.sin(math.pi * u) * ramp
            else:
                # Stance phase: push backward
                hip_target = self.hip_stand_mag(leg) + (HIP_FORWARD_EXT - (HIP_FORWARD_EXT + HIP_BACK_EXT) * u) * ramp
                knee_target = KNEE_STAND
            
            self.hips[leg].setPosition(self.clamp(self.hip_cmd(leg, hip_target), -0.8, 0.8))
            self.knees[leg].setPosition(self.clamp(knee_target, -1.5, 0.1))
    
    def update_navigation(self):
        """Update delivery system and convert to movement commands"""
        self.delivery.update()
        
        # Determine if should walk
        if self.delivery.state == "NAVIGATING":
            current_pos = self.delivery.get_robot_position()
            target_pos = DELIVERY_POINTS[self.delivery.current_target]
            distance = math.sqrt((current_pos[0] - target_pos[0])**2 + (current_pos[1] - target_pos[1])**2)
            
            # Start walking if far from target
            if distance > WAYPOINT_TOLERANCE and not self.delivery.should_avoid_obstacle():
                self.is_walking = True
                self.walk_timer = 10.0  # Walk for up to 10 seconds before recheck
            else:
                self.is_walking = False
        
        elif self.delivery.state == "DELIVERING":
            self.is_walking = False
        
        elif self.delivery.state == "RETURNING":
            current_pos = self.delivery.get_robot_position()
            home_pos = DELIVERY_POINTS["HOME"]
            distance = math.sqrt((current_pos[0] - home_pos[0])**2 + (current_pos[1] - home_pos[1])**2)
            
            if distance > WAYPOINT_TOLERANCE and not self.delivery.should_avoid_obstacle():
                self.is_walking = True
                self.walk_timer = 10.0
            else:
                self.is_walking = False
        
        else:  # IDLE
            self.is_walking = False
    
    def run(self):
        """Main robot control loop"""
        print("[ROBOT] Starting initialization sequence...")
        
        # Phase 1: Stand up
        print("[ROBOT] Standing up...")
        for _ in range(int(SETTLE_TIME / (self.timestep / 1000))):
            self.robot.step(self.timestep)
            self.apply_stand_pose()
        
        print("[ROBOT] Ready for delivery!")
        print("[ROBOT] Starting delivery route...")
        self.delivery.start_delivery_route()
        
        self.walk_start_time = self.robot.getTime()
        status_print_time = 0.0
        
        # Main loop
        while self.robot.step(self.timestep) != -1:
            current_time = self.robot.getTime()
            elapsed = current_time - self.walk_start_time
            
            # Update navigation
            self.update_navigation()
            
            # Apply gait or stand
            if self.is_walking and self.delivery.battery_level > 5:
                ramp = self.clamp(elapsed / RAMP_TIME, 0.0, 1.0)
                self.apply_walk_gait(elapsed, ramp)
            else:
                self.apply_stand_pose()
            
            # Print status periodically
            if current_time - status_print_time > 5.0:
                self.delivery.print_status()
                status_print_time = current_time
            
            # Check if all deliveries complete and returned home
            if self.delivery.state == "IDLE":
                print("\n[ROBOT] All deliveries complete! Waiting for next instruction...")
                print("[ROBOT] To start new deliveries, restart or send command")
                # Can break or wait for new commands
                break
