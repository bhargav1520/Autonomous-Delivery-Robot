"""
DEVICE VERIFICATION CHECKLIST
Verify all these sensors and motors exist in your hexapod.proto file
"""

# ===== REQUIRED SENSORS =====
# These MUST exist and be correctly named in your hexapod.proto

SENSOR_CHECKLIST = {
    "gps": {
        "type": "GPS",
        "purpose": "Absolute position tracking (x, y, z)",
        "used_for": "Navigation, waypoint reaching",
        "in_proto": "DEF gps GPS { ... }",
        "check": "Select robot in Webots → expand in tree → look for 'gps' entry"
    },
    
    "compass": {
        "type": "Compass",
        "purpose": "Heading direction (returns unit vector)",
        "used_for": "Steering angle calculation",
        "in_proto": "DEF compass Compass { ... }",
        "check": "Should read [-1..1, -1..1, -1..1] values"
    },
    
    "ds_front": {
        "type": "DistanceSensor",
        "purpose": "Detect obstacle ahead",
        "used_for": "Obstacle avoidance trigger",
        "in_proto": "DEF ds_front DistanceSensor { ... rotation 0 0 1 0 ... }",
        "check": "Should point in +Z direction (forward)"
    },
    
    "ds_left": {
        "type": "DistanceSensor",
        "purpose": "Detect obstacle to left",
        "used_for": "Avoidance direction choice",
        "in_proto": "DEF ds_left DistanceSensor { ... rotation 0 0 1 1.57 ... }",
        "check": "Should point in -X direction (left)"
    },
    
    "ds_right": {
        "type": "DistanceSensor",
        "purpose": "Detect obstacle to right",
        "used_for": "Avoidance direction choice",
        "in_proto": "DEF ds_right DistanceSensor { ... rotation 0 0 1 -1.57 ... }",
        "check": "Should point in +X direction (right)"
    },
    
    "ds_back": {
        "type": "DistanceSensor",
        "purpose": "Detect obstacle behind",
        "used_for": "Prevent reversing into obstacles",
        "in_proto": "DEF ds_back DistanceSensor { ... rotation 0 0 1 3.14 ... }",
        "check": "Should point in -Z direction (backward)"
    },
    
    "display": {
        "type": "Display",
        "purpose": "Real-time mini-map rendering",
        "used_for": "Visual feedback of robot and waypoints",
        "in_proto": "DEF display Display { width 200 height 200 }",
        "check": "OPTIONAL - if not present, mini-map is disabled with warning"
    },
    
    "keyboard": {
        "type": "Keyboard",
        "purpose": "User input for delivery commands",
        "used_for": "Control panel (S/A/B/C/D/Q/P keys)",
        "in_proto": "Keyboard { }",
        "check": "Usually built-in, check simulation settings"
    }
}

# ===== REQUIRED MOTORS =====
# Hexapod has 6 legs, each with 2 motors (hip and knee)
# Total: 12 motors

MOTOR_NAMING_SCHEME = """
Leg 0 (motor pair 0-1):    leg_0_hip, leg_0_knee
Leg 1 (motor pair 2-3):    leg_1_hip, leg_1_knee
Leg 2 (motor pair 4-5):    leg_2_hip, leg_2_knee
Leg 3 (motor pair 6-7):    leg_3_hip, leg_3_knee
Leg 4 (motor pair 8-9):    leg_4_hip, leg_4_knee
Leg 5 (motor pair 10-11):  leg_5_hip, leg_5_knee

Total: 12 motors (6 legs × 2 joints)
"""

MOTOR_CHECKLIST = {
    "leg_0_hip": "Front-left hip joint",
    "leg_0_knee": "Front-left knee joint",
    "leg_1_hip": "Middle-left hip joint",
    "leg_1_knee": "Middle-left knee joint",
    "leg_2_hip": "Back-left hip joint",
    "leg_2_knee": "Back-left knee joint",
    "leg_3_hip": "Front-right hip joint",
    "leg_3_knee": "Front-right knee joint",
    "leg_4_hip": "Middle-right hip joint",
    "leg_4_knee": "Middle-right knee joint",
    "leg_5_hip": "Back-right hip joint",
    "leg_5_knee": "Back-right knee joint",
}


# ===== HOW TO VERIFY DEVICES IN YOUR HEXAPOD.PROTO =====

VERIFICATION_STEPS = """
1. OPEN YOUR HEXAPOD.PROTO FILE

2. LOOK FOR SENSOR DEFINITIONS - They should appear in robot's 'children' list:

   Example GPS:
   GPS {
     translation 0 0 0
     rotation 0 0 1 0
   }
   
   OR with DEF name:
   DEF gps GPS {
     translation 0 0 0
     rotation 0 0 1 0
   }

3. LOOK FOR MOTOR DEFINITIONS - They should be in Joint/HingeJoint nodes:

   Example motor:
   HingeJoint {
     jointParameters HingeJointParameters {
       axis 1 0 0
       anchor 0 0.1 0.1
     }
     device [
       MotorSpeed { name "leg_0_hip" maxVelocity 2.0 }
     ]
     endPoint Solid {
       ...
     }
   }

4. IN WEBOTS GUI RUNTIME CHECK:

   - Click on robot node in scene tree
   - Go to Inspector panel (right side)
   - Look for "devices" field
   - Should list all sensors and motors
   - Click on each → verify it appears correctly

5. IF DEVICES ARE MISSING:

   Option A: Rename existing motors to match the scheme above
   
   Option B: If using different naming, update motor_name variables in controller:
   
   # In the __init__ method of DeliveryRobot class:
   # Change from:
   motor_name = f"leg_{leg}_{joint}"
   # To:
   motor_name = "your_actual_motor_name"

6. IF SENSORS ARE MISSING:

   A: GPS/Compass not found → Add them to hexapod.proto children
   B: Distance sensors not found → Add all 4 with correct rotations
   C: Display not found → Mini-map will be disabled (non-critical)
   D: Keyboard not found → Controls will be disabled (non-critical)


MINIMAL WORKING SETUP:
- GPS (required)
- Compass (required)
- At least 1 distance sensor (ds_front is critical)
- 12 motors matching the naming scheme

FULL WORKING SETUP:
- All above +
- All 4 distance sensors (ds_front, ds_left, ds_right, ds_back)
- Display (for mini-map)
- Keyboard (for controls)
"""


# ===== QUICK REFERENCE FOR .PROTO EDITS =====

PROTO_TEMPLATE_SNIPPET = """
# If you need to ADD sensors to your hexapod.proto, here's a template:

Proto Hexapod [
  field SFVec3f    translation  0 0 0
  field SFRotation rotation     0 0 1 0
  # ... other fields ...
] {
  Robot {
    children [
      # === SENSORS ===
      
      DEF gps GPS {
        translation 0 0 0
      }
      
      DEF compass Compass {
        translation 0 0 0
      }
      
      # Distance sensors pointing in 4 directions
      DEF ds_front DistanceSensor {
        translation 0 -0.05 0.2
        rotation 0 0 1 0
        lookupTable [ 0 0 0, 1 0 0 ]
        numberOfRays 1
      }
      
      DEF ds_left DistanceSensor {
        translation -0.2 -0.05 0
        rotation 0 0 1 1.5708
        lookupTable [ 0 0 0, 1 0 0 ]
        numberOfRays 1
      }
      
      DEF ds_right DistanceSensor {
        translation 0.2 -0.05 0
        rotation 0 0 1 -1.5708
        lookupTable [ 0 0 0, 1 0 0 ]
        numberOfRays 1
      }
      
      DEF ds_back DistanceSensor {
        translation 0 -0.05 -0.2
        rotation 0 0 1 3.14159
        lookupTable [ 0 0 0, 1 0 0 ]
        numberOfRays 1
      }
      
      # === MOTOR EXAMPLE (for each leg) ===
      
      HingeJoint {
        jointParameters HingeJointParameters {
          axis 1 0 0
          anchor 0 0.1 0.1
        }
        device [
          MotorSpeed { name "leg_0_hip" maxVelocity 3.0 }
        ]
        endPoint Solid {
          # knee joint definition follows...
        }
      }
      
      # Repeat similar structure for all 12 motors
      
    ]
    # ...rest of robot definition...
  }
}
"""

print("DEVICE VERIFICATION CHECKLIST")
print("=" * 60)
print(VERIFICATION_STEPS)
