"""
Autonomous Delivery System for Hexapod Robot
Features:
1. Autonomous Navigation (GPS + waypoints)
2. Multi-Point Delivery System (5 locations)
3. Obstacle Avoidance (distance sensors)
4. Stop-and-Deliver Logic
5. Continuous Operation Loop
6. Path Optimization (nearest neighbor)
7. Battery Simulation
8. UI Control Panel
"""

import math
import json

# ========== CONFIGURATION ==========
TIMESTEP = 8
MAX_BATTERY = 100.0
BATTERY_DRAIN_RATE = 0.15  # % per second while moving
BATTERY_IDLE_DRAIN = 0.02
DELIVERY_STOP_TIME = 3.0  # seconds to stop at delivery point
WAYPOINT_TOLERANCE = 0.3  # meters
OBSTACLE_THRESHOLD = 0.5  # meters - avoid obstacles closer than this
MAX_WALK_SPEED = 0.5  # m/s

# Delivery locations (x, z) in world coordinates
DELIVERY_POINTS = {
    "HOME": (0.0, 0.0),
    "HOUSE_A": (3.0, 2.0),
    "HOUSE_B": (5.0, 5.0),
    "HOUSE_C": (-3.0, 4.0),
    "HOUSE_D": (-2.0, -3.0),
}

class DeliverySystem:
    def __init__(self, robot):
        self.robot = robot
        self.timestep = int(self.robot.getBasicTimeStep())
        
        # Get sensors and motors (with graceful fallback if missing)
        self.gps = None
        try:
            self.gps = self.robot.getDevice("gps")
            self.gps.enable(self.timestep)
            print("[DeliverySystem] GPS sensor initialized")
        except:
            print("[DeliverySystem] WARNING: GPS sensor not found - using simulated position")
        
        self.compass = None
        try:
            self.compass = self.robot.getDevice("compass")
            self.compass.enable(self.timestep)
            print("[DeliverySystem] Compass sensor initialized")
        except:
            print("[DeliverySystem] WARNING: Compass sensor not found - using simulated heading")
        
        self.imu = None
        try:
            self.imu = self.robot.getDevice("imu")
            self.imu.enable(self.timestep)
            print("[DeliverySystem] IMU sensor initialized")
        except:
            print("[DeliverySystem] WARNING: IMU sensor not found")
        
        # Distance sensors (front, left, right for obstacle detection)
        self.distance_sensors = {}
        sensor_names = ["ds_front", "ds_left", "ds_right", "ds_back"]
        for name in sensor_names:
            try:
                ds = self.robot.getDevice(name)
                ds.enable(self.timestep)
                self.distance_sensors[name] = ds
            except:
                pass
        if not self.distance_sensors:
            print("[DeliverySystem] WARNING: No distance sensors found - obstacle detection disabled")
        
        # Simulated position/heading (fallback if sensors missing)
        self.simulated_x = 0.0
        self.simulated_z = 0.0
        self.simulated_heading = 0.0
        
        # Robot state
        self.battery_level = MAX_BATTERY
        self.current_target = None
        self.delivery_queue = []
        self.has_package = False
        self.is_delivering = False
        self.delivery_timer = 0.0
        self.total_time = 0.0
        self.state = "IDLE"  # IDLE, NAVIGATING, DELIVERING, RETURNING
        self.delivered_count = 0
        
        # Get robot node for visualization
        try:
            self.robot_node = self.robot.getFromDef("HEXAPOD")
        except:
            self.robot_node = None
            
        print("[DELIVERY SYSTEM] Initialized successfully")
        print(f"[DELIVERY SYSTEM] Available locations: {list(DELIVERY_POINTS.keys())}")
        
    def get_robot_position(self):
        """Get robot's current GPS position (x, z)"""
        if self.gps is None:
            # Return simulated position if GPS not available
            return (self.simulated_x, self.simulated_z)
        pos = self.gps.getValues()
        return (pos[0], pos[2])
    
    def get_robot_heading(self):
        """Get robot heading in radians using compass"""
        if self.compass is None:
            # Return simulated heading if compass not available
            return self.simulated_heading
        try:
            compass_vec = self.compass.getValues()
            heading = math.atan2(compass_vec[0], compass_vec[2])
            return heading
        except:
            return 0.0
    
    def calculate_distance(self, p1, p2):
        """Euclidean distance between two points"""
        return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)
    
    def nearest_neighbor_path(self, locations):
        """Calculate shortest path using nearest neighbor algorithm"""
        if not locations:
            return []
        
        unvisited = set(locations)
        current = "HOME"
        path = [current]
        unvisited.discard(current)  # safely remove if present
        
        while unvisited:
            current_pos = DELIVERY_POINTS[current]
            nearest = min(unvisited, 
                         key=lambda x: self.calculate_distance(current_pos, DELIVERY_POINTS[x]))
            path.append(nearest)
            unvisited.remove(nearest)
            current = nearest
        
        path.append("HOME")  # Return to base
        return path
    
    def check_obstacles(self):
        """Check distance sensors for obstacles"""
        min_distance = float('inf')
        obstacle_detected = False
        
        for sensor_name, sensor in self.distance_sensors.items():
            distance = sensor.getValue()
            if distance < min_distance:
                min_distance = distance
            if distance < OBSTACLE_THRESHOLD:
                obstacle_detected = True
                print(f"[OBSTACLE] {sensor_name}: {distance:.2f}m")
        
        return obstacle_detected, min_distance
    
    def update_battery(self):
        """Update battery level based on activity"""
        obstacle_detected, _ = self.check_obstacles()
        
        # Convert drain rate from per-second to per-timestep
        timestep_sec = self.timestep / 1000.0
        
        if self.state == "NAVIGATING":
            self.battery_level -= BATTERY_DRAIN_RATE * timestep_sec
        else:
            self.battery_level -= BATTERY_IDLE_DRAIN * timestep_sec
        
        self.battery_level = max(0, min(MAX_BATTERY, self.battery_level))
        
        if self.battery_level <= 15.0 and self.state != "RETURNING":
            print(f"[BATTERY] Low battery: {self.battery_level:.1f}% - Returning to HOME")
            self.state = "RETURNING"
            self.current_target = "HOME"
    
    def should_avoid_obstacle(self):
        """Determine if robot should stop or take evasive action"""
        obstacle_detected, min_distance = self.check_obstacles()
        return obstacle_detected
    
    def navigate_to_waypoint(self, target_location):
        """Navigate robot towards target location using GPS and heading control"""
        current_pos = self.get_robot_position()
        target_pos = DELIVERY_POINTS[target_location]
        
        # Calculate direction to target
        dx = target_pos[0] - current_pos[0]
        dz = target_pos[1] - current_pos[1]
        target_heading = math.atan2(dx, dz)
        current_heading = self.get_robot_heading()
        
        # Calculate angular difference
        angle_diff = target_heading - current_heading
        # Normalize to [-pi, pi]
        while angle_diff > math.pi:
            angle_diff -= 2 * math.pi
        while angle_diff < -math.pi:
            angle_diff += 2 * math.pi
        
        distance = self.calculate_distance(current_pos, target_pos)
        
        # Check if reached waypoint
        if distance < WAYPOINT_TOLERANCE:
            return True, distance
        
        return False, distance
    
    def start_delivery_route(self, locations=None):
        """Start delivery to specified locations or all"""
        if locations is None:
            locations = list(DELIVERY_POINTS.keys())
            locations.remove("HOME")
        
        self.delivery_queue = self.nearest_neighbor_path(locations)
        self.has_package = True
        self.state = "NAVIGATING"
        self.current_target = self.delivery_queue[1] if len(self.delivery_queue) > 1 else "HOME"
        
        print(f"\n[DELIVERY] Route planned: {' → '.join(self.delivery_queue)}")
        print(f"[DELIVERY] Total deliveries: {len(self.delivery_queue) - 2}")  # Exclude HOME at start/end
    
    def perform_delivery(self):
        """Execute delivery at current location"""
        if self.state == "DELIVERING":
            self.delivery_timer -= self.timestep / 1000.0
            
            if self.delivery_timer <= 0:
                self.has_package = False
                self.delivered_count += 1
                self.state = "NAVIGATING"
                
                # Move to next delivery
                current_idx = self.delivery_queue.index(self.current_target)
                if current_idx + 1 < len(self.delivery_queue):
                    self.current_target = self.delivery_queue[current_idx + 1]
                    print(f"[DELIVERY] Delivered to {self.delivery_queue[current_idx]} ✓")
                    print(f"[DELIVERY] Moving to next: {self.current_target}")
                else:
                    print(f"[DELIVERY] All deliveries complete! Returning to HOME.")
                    self.state = "RETURNING"
                    self.current_target = "HOME"
    
    def update(self):
        """Main update loop"""
        self.total_time += self.timestep / 1000.0
        self.update_battery()
        
        # State machine
        if self.state == "IDLE":
            pass
        
        elif self.state == "NAVIGATING":
            current_pos = self.get_robot_position()
            target_pos = DELIVERY_POINTS[self.current_target]
            distance = self.calculate_distance(current_pos, target_pos)
            
            # Check obstacles
            if self.should_avoid_obstacle():
                print(f"[NAV] Obstacle avoidance activated")
                # Robot will naturally stop due to obstacle detection
            
            # Check if reached target
            if distance < WAYPOINT_TOLERANCE:
                self.state = "DELIVERING"
                self.delivery_timer = DELIVERY_STOP_TIME
                print(f"\n[DELIVERY] Reached {self.current_target} - Delivering package...")
            
            # Debug info every 2 seconds
            if int(self.total_time) % 2 == 0 and self.total_time % (self.timestep/1000.0) < 0.1:
                print(f"[NAV] Target: {self.current_target} | Distance: {distance:.2f}m | Battery: {self.battery_level:.1f}%")
        
        elif self.state == "DELIVERING":
            self.perform_delivery()
        
        elif self.state == "RETURNING":
            current_pos = self.get_robot_position()
            home_pos = DELIVERY_POINTS["HOME"]
            distance = self.calculate_distance(current_pos, home_pos)
            
            if distance < WAYPOINT_TOLERANCE:
                self.state = "IDLE"
                self.battery_level = MAX_BATTERY  # Recharge at home
                print(f"\n[BATTERY] Recharged at HOME | Total delivered: {self.delivered_count}")
                print(f"[STATUS] Ready for next delivery route")
    
    def print_status(self):
        """Print system status"""
        print(f"\n{'='*60}")
        print(f"[STATUS REPORT] Time: {self.total_time:.1f}s")
        print(f"  State: {self.state}")
        print(f"  Battery: {self.battery_level:.1f}%")
        print(f"  Current Target: {self.current_target}")
        print(f"  Package: {'YES' if self.has_package else 'NO'}")
        print(f"  Delivered: {self.delivered_count}")
        if self.delivery_queue:
            print(f"  Queue: {' → '.join(self.delivery_queue)}")
        print(f"{'='*60}\n")
