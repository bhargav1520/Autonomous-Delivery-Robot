"""
CONFIGURATION FILE - Autonomous Delivery System
Modify these settings to customize robot behavior
"""

# ========== BATTERY SYSTEM ==========
BATTERY_CONFIG = {
    "max_capacity": 100.0,           # Maximum battery percentage
    "drain_rate_moving": 0.15,       # % per second while navigating
    "drain_rate_idle": 0.02,         # % per second while stationary
    "low_battery_threshold": 15.0,   # % below which robot returns to base
    "recharge_rate": 50.0,           # % per second while at HOME
}

# ========== NAVIGATION PARAMETERS ==========
NAVIGATION_CONFIG = {
    "waypoint_tolerance": 0.3,       # Distance threshold to consider waypoint reached (meters)
    "max_walk_speed": 0.5,           # Maximum walking speed (m/s)
    "gait_frequency": 1.2,           # Walking stride frequency (Hz)
    "ramp_time": 1.5,                # Time to ramp up from stand to full walk (seconds)
}

# ========== DELIVERY SYSTEM ==========
DELIVERY_CONFIG = {
    "delivery_stop_time": 3.0,       # Time to pause at delivery location (seconds)
    "package_weight": 1.0,           # Package mass (kg) - for battery drain
}

# ========== OBSTACLE AVOIDANCE ==========
OBSTACLE_CONFIG = {
    "front_threshold": 0.5,          # Front sensor detection range (meters)
    "side_threshold": 0.5,           # Side sensor detection range (meters)
    "back_threshold": 0.5,           # Rear sensor detection range (meters)
    "min_safe_distance": 0.3,        # Minimum distance to obstacle (meters)
}

# ========== DELIVERY LOCATIONS ==========
# Format: "LOCATION_NAME": (x_coordinate, z_coordinate)
# Coordinates should match your Webots world file
DELIVERY_LOCATIONS = {
    "HOME": (0.0, 0.0),              # Base station (starting point)
    "HOUSE_A": (3.0, 2.0),           # Primary delivery point
    "HOUSE_B": (5.0, 5.0),           # Secondary delivery point
    "HOUSE_C": (-3.0, 4.0),          # Tertiary delivery point
    "HOUSE_D": (-2.0, -3.0),         # Quaternary delivery point
    # Add more locations as needed:
    # "WAREHOUSE": (10.0, 0.0),
    # "STORE_A": (-5.0, 5.0),
}

# ========== GAIT PARAMETERS ==========
GAIT_CONFIG = {
    "hip_front_stand": 0.24,         # Front leg hip angle when standing
    "hip_rear_stand": 0.20,          # Rear leg hip angle when standing
    "knee_stand": 0.0,               # Knee position when standing (within -0.02 to 0.02 slider range)
    "hip_forward_extension": 0.50,   # Increased forward reach for propulsion
    "hip_back_extension": 0.50,      # Increased backward push for propulsion
    "knee_lift": 0.015,              # Small lift within slider range (±0.02m = ±2cm)
}

# ========== UI / DISPLAY SETTINGS ==========
UI_CONFIG = {
    "status_print_interval": 3.0,    # Print status every N seconds
    "display_width": 400,            # Display panel width (pixels)
    "display_height": 400,           # Display panel height (pixels)
    "show_detailed_logs": True,      # Enable detailed console logging
}

# ========== SIMULATION SETTINGS ==========
SIM_CONFIG = {
    "timestep": 8,                   # Physics simulation timestep (milliseconds)
    "sensor_update_interval": 8,     # Sensor update rate (milliseconds)
    "max_simulation_time": 3600.0,   # Max sim time before auto-stop (seconds)
}

# ========== ROBOT SPECIFICATIONS ==========
ROBOT_SPECS = {
    "name": "HexapodDeliveryBot",
    "legs": 6,
    "motor_type": "Stepper Motors",
    "max_torque": 10.0,              # Motor max torque (Nm) - matches Webots motor limits
    "max_velocity": 3.0,             # Motor max velocity (rad/s)
    "mass": 5.0,                     # Total mass (kg)
    "max_payload": 2.0,              # Max package weight (kg)
}

# ========== CONTROL MAPPINGS ==========
KEYBOARD_CONTROLS = {
    'S': 'Start all deliveries',
    'A': 'Deliver to HOUSE_A',
    'B': 'Deliver to HOUSE_B',
    'C': 'Deliver to HOUSE_C',
    'D': 'Deliver to HOUSE_D',
    'Q': 'Stop and return to HOME',
    'P': 'Print status report',
    'H': 'Print help menu',
    'R': 'Reset robot position',
}

# ========== ADVANCED SETTINGS ==========
ADVANCED_CONFIG = {
    "enable_battery_simulation": True,
    "enable_obstacle_avoidance": True,
    "enable_auto_recharge": True,
    "enable_path_optimization": True,
    "enable_debug_logging": False,
    "use_realistic_physics": True,
    "allow_multi_robot": False,
}

# ========== PATH OPTIMIZATION ALGORITHMS ==========
PATH_OPTIMIZATION = {
    "algorithm": "nearest_neighbor",  # Options: "nearest_neighbor", "greedy", "tsp_approx"
    "recalculate_on_obstacle": True,
    "use_cached_paths": True,
}

# ========== LOGGING CONFIGURATION ==========
LOGGING_CONFIG = {
    "log_file": "delivery_log.txt",
    "log_level": "INFO",  # DEBUG, INFO, WARNING, ERROR
    "save_statistics": True,
    "statistics_file": "delivery_stats.csv",
}

def get_delivery_location(location_name):
    """Get coordinates for a delivery location"""
    return DELIVERY_LOCATIONS.get(location_name, None)

def get_all_delivery_locations():
    """Get all available delivery locations"""
    return list(DELIVERY_LOCATIONS.keys())

def validate_configuration():
    """Validate configuration consistency"""
    errors = []
    warnings = []
    
    # Check battery settings
    if BATTERY_CONFIG["max_capacity"] <= 0:
        errors.append("Battery capacity must be positive")
    if BATTERY_CONFIG["drain_rate_moving"] < 0:
        errors.append("Battery drain rate cannot be negative")
    
    # Check navigation settings
    if NAVIGATION_CONFIG["waypoint_tolerance"] < 0.05:
        warnings.append("Waypoint tolerance very small - may cause oscillation")
    if NAVIGATION_CONFIG["max_walk_speed"] <= 0:
        errors.append("Max walk speed must be positive")
    
    # Check delivery locations
    if not DELIVERY_LOCATIONS or "HOME" not in DELIVERY_LOCATIONS:
        errors.append("HOME location must be defined")
    if len(DELIVERY_LOCATIONS) < 2:
        warnings.append("Only one delivery location defined")
    
    # Check gait parameters
    if abs(GAIT_CONFIG["knee_stand"]) < 0.5:
        warnings.append("Knee stand angle may be too shallow")
    
    return errors, warnings

def print_configuration_summary():
    """Print a summary of current configuration"""
    print("\n" + "="*70)
    print("DELIVERY SYSTEM CONFIGURATION SUMMARY")
    print("="*70)
    
    print("\n[BATTERY]")
    print(f"  Capacity: {BATTERY_CONFIG['max_capacity']}%")
    print(f"  Drain (moving): {BATTERY_CONFIG['drain_rate_moving']}%/s")
    print(f"  Drain (idle): {BATTERY_CONFIG['drain_rate_idle']}%/s")
    print(f"  Low threshold: {BATTERY_CONFIG['low_battery_threshold']}%")
    
    print("\n[NAVIGATION]")
    print(f"  Waypoint tolerance: {NAVIGATION_CONFIG['waypoint_tolerance']}m")
    print(f"  Max speed: {NAVIGATION_CONFIG['max_walk_speed']}m/s")
    print(f"  Gait frequency: {NAVIGATION_CONFIG['gait_frequency']}Hz")
    
    print("\n[DELIVERY]")
    print(f"  Stop time: {DELIVERY_CONFIG['delivery_stop_time']}s")
    print(f"  Locations: {len(DELIVERY_LOCATIONS)}")
    for name, coords in DELIVERY_LOCATIONS.items():
        print(f"    - {name}: ({coords[0]}, {coords[1]})")
    
    print("\n[OBSTACLES]")
    print(f"  Front threshold: {OBSTACLE_CONFIG['front_threshold']}m")
    print(f"  Min safe distance: {OBSTACLE_CONFIG['min_safe_distance']}m")
    
    print("\n[ADVANCED]")
    print(f"  Battery simulation: {ADVANCED_CONFIG['enable_battery_simulation']}")
    print(f"  Obstacle avoidance: {ADVANCED_CONFIG['enable_obstacle_avoidance']}")
    print(f"  Path optimization: {ADVANCED_CONFIG['enable_path_optimization']}")
    
    # Validate
    errors, warnings = validate_configuration()
    if errors:
        print("\n[ERRORS]")
        for error in errors:
            print(f"  ❌ {error}")
    if warnings:
        print("\n[WARNINGS]")
        for warning in warnings:
            print(f"  ⚠️  {warning}")
    
    if not errors and not warnings:
        print("\n✅ Configuration valid")
    
    print("="*70 + "\n")

# ========== AUTO-LOAD VALIDATION ==========
if __name__ == "__main__":
    print_configuration_summary()
