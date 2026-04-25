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

from controller import Supervisor
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
CRITICAL_OBSTACLE_THRESHOLD = 0.25  # meters - very close, need immediate action
SAFE_DISTANCE = 0.7  # meters - safe to proceed forward
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
    def __init__(self, robot=None):
        # Accept robot instance instead of creating new Supervisor
        if robot is None:
            self.robot = Supervisor()
        else:
            self.robot = robot
            
        self.timestep = int(self.robot.getBasicTimeStep())
        
        # Get sensors and motors
        self.gps = self.robot.getDevice("gps")
        self.gps.enable(self.timestep)
        
        self.compass = self.robot.getDevice("compass")
        self.compass.enable(self.timestep)
        
        self.imu = self.robot.getDevice("imu")
        self.imu.enable(self.timestep)
        
        # Distance sensors (front, left, right for obstacle detection)
        self.distance_sensors = {}
        sensor_names = ["ds_front", "ds_left", "ds_right", "ds_back"]
        for name in sensor_names:
            try:
                ds = self.robot.getDevice(name)
                if ds is not None:
                    ds.enable(self.timestep)
                    self.distance_sensors[name] = ds
                    print(f"[SENSORS] Successfully enabled {name}")
                else:
                    print(f"[SENSORS] Warning: {name} not found in robot model")
            except Exception as e:
                print(f"[SENSORS] Failed to initialize {name}: {e}")
        
        if not self.distance_sensors:
            print("[SENSORS] WARNING: No distance sensors found! Obstacle avoidance disabled.")
        else:
            print(f"[SENSORS] ✓ Initialized {len(self.distance_sensors)} distance sensors for obstacle detection")
        
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
        pos = self.gps.getValues()
        return (pos[0], pos[2])
    
    def get_robot_heading(self):
        """Get robot heading in radians using compass"""
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
        unvisited.remove(current)
        
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
        """Check distance sensors for obstacles and evaluate all directions
        Returns: (obstacle_detected, min_distance, best_escape_direction, clearances_dict)
        best_escape_direction: 'FORWARD', 'LEFT', 'RIGHT', 'BACK', or 'NONE'
        clearances_dict: {'front': dist, 'left': dist, 'right': dist, 'back': dist}
        """
        if not self.distance_sensors:
            # No sensors available
            return False, float('inf'), 'FORWARD', {'front': float('inf'), 'left': float('inf'), 'right': float('inf'), 'back': float('inf')}
        
        clearances = {
            'front': 10.0,  # Default: far away (no obstacle)
            'left': 10.0,
            'right': 10.0,
            'back': 10.0,
        }
        
        # Scan all sensors and build clearance map
        for sensor_name, sensor in self.distance_sensors.items():
            try:
                raw_value = sensor.getValue()
                # In Webots, sensor.getValue() returns the actual distance in meters
                # When nothing is detected, it typically returns a large value or 0
                distance = float(raw_value)
                
                # Treat 0 or negative values as "no obstacle" (out of range)
                if distance <= 0:
                    distance = 10.0
                    
            except Exception as e:
                distance = 10.0
                print(f"[SENSOR ERROR] {sensor_name}: {e}")
            
            sensor_lower = sensor_name.lower()
            if 'front' in sensor_lower or 'forward' in sensor_lower:
                clearances['front'] = min(clearances['front'], distance)
            elif 'left' in sensor_lower:
                clearances['left'] = min(clearances['left'], distance)
            elif 'right' in sensor_lower:
                clearances['right'] = min(clearances['right'], distance)
            elif 'back' in sensor_lower:
                clearances['back'] = min(clearances['back'], distance)
        
        # Determine if obstacle is detected (distance < threshold)
        obstacle_detected = any(d < OBSTACLE_THRESHOLD for d in clearances.values())
        min_distance = min(clearances.values())
        
        # Calculate best escape direction intelligently
        best_escape = self._find_best_escape(clearances)
        
        return obstacle_detected, min_distance, best_escape, clearances
    
    def _find_best_escape(self, clearances):
        """Find the best direction to escape based on available clearances
        Priority:
        1. If front is clear and safe, move forward
        2. Check left/right for the clearest path
        3. If trapped, move backward
        """
        front = clearances.get('front', 0)
        left = clearances.get('left', 0)
        right = clearances.get('right', 0)
        back = clearances.get('back', 0)
        
        # If front is sufficiently clear, go forward
        if front >= SAFE_DISTANCE:
            return 'FORWARD'
        
        # Find best side (left or right)
        if left > right and left >= OBSTACLE_THRESHOLD:
            return 'LEFT'
        elif right >= OBSTACLE_THRESHOLD:
            return 'RIGHT'
        
        # If sides are blocked but back is clear, move backward
        if back >= OBSTACLE_THRESHOLD:
            return 'BACK'
        
        # All blocked or critical - move backward to create space
        if min(left, right) < CRITICAL_OBSTACLE_THRESHOLD:
            return 'BACK_HARD'  # Reverse with urgency
        
        return 'STOP'  # Fully trapped
    
    def update_battery(self):
        """Update battery level based on activity"""
        obstacle_detected, _, _, _ = self.check_obstacles()
        
        if self.state == "NAVIGATING":
            self.battery_level -= BATTERY_DRAIN_RATE
        else:
            self.battery_level -= BATTERY_IDLE_DRAIN
        
        self.battery_level = max(0, min(MAX_BATTERY, self.battery_level))
        
        if self.battery_level <= 15.0 and self.state != "RETURNING":
            print(f"[BATTERY] Low battery: {self.battery_level:.1f}% - Returning to HOME")
            self.state = "RETURNING"
            self.current_target = "HOME"
    
    def should_avoid_obstacle(self):
        """Determine if robot should take evasive action"""
        obstacle_detected, _, _, _ = self.check_obstacles()
        return obstacle_detected
    
    def get_obstacle_direction(self):
        """Get the best escape direction from obstacles
        Returns: 'FORWARD', 'LEFT', 'RIGHT', 'BACK', 'BACK_HARD', 'STOP', or None
        """
        _, _, best_escape, _ = self.check_obstacles()
        return best_escape
    
    def get_clearances(self):
        """Get clearance distances in all directions
        Returns: dict with keys 'front', 'left', 'right', 'back'
        """
        _, _, _, clearances = self.check_obstacles()
        return clearances
    
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


