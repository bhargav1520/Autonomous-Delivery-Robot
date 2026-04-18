# WEBOTS WORLD SETUP GUIDE
# Instructions for configuring hexapod.wbt to work with Autonomous Delivery System

## 🎯 Quick Setup Steps

### 1. Add Required Sensors to Hexapod Robot

The delivery system requires these sensors to be present in your robot definition:

**In hexapod.proto or hexapod node:**

```
# GPS Sensor (for position tracking)
GPS {
  name "gps"
  accuracy 0.01
}

# Compass Sensor (for heading/direction)
Compass {
  name "compass"
  accuracy 0.01
}

# IMU Sensor (for balance - already likely present)
InertialUnit {
  name "imu"
}

# Distance Sensors (for obstacle detection)
# Add these around the robot body:

# Front obstacle sensor
DistanceSensor {
  translation 0.2 0 0       # Forward position
  rotation 0 1 0 0
  name "ds_front"
  lookupTable [
    0 1000 0
    0.5 0 0
  ]
  type "sonar"
}

# Left obstacle sensor
DistanceSensor {
  translation 0 0 0.2       # Left position
  rotation 0 1 0 1.5708     # 90 degrees
  name "ds_left"
  lookupTable [
    0 1000 0
    0.5 0 0
  ]
  type "sonar"
}

# Right obstacle sensor
DistanceSensor {
  translation 0 0 -0.2      # Right position
  rotation 0 1 0 -1.5708    # -90 degrees
  name "ds_right"
  lookupTable [
    0 1000 0
    0.5 0 0
  ]
  type "sonar"
}

# Back obstacle sensor
DistanceSensor {
  translation -0.2 0 0      # Backward position
  rotation 0 1 0 3.1416     # 180 degrees
  name "ds_back"
  lookupTable [
    0 1000 0
    0.5 0 0
  ]
  type "sonar"
}
```

### 2. Add Delivery Location Markers (Optional Visual Aids)

Add sphere objects at each delivery point for visualization:

```
# HOUSE_A marker (3, 0, 2)
Solid {
  translation 3 0.1 2
  children [
    Shape {
      appearance Appearance {
        material Material { diffuseColor 1 0 0 }  # Red
      }
      geometry Sphere { radius 0.2 }
    }
  ]
}

# HOUSE_B marker (5, 0, 5)
Solid {
  translation 5 0.1 5
  children [
    Shape {
      appearance Appearance {
        material Material { diffuseColor 0 1 0 }  # Green
      }
      geometry Sphere { radius 0.2 }
    }
  ]
}

# HOUSE_C marker (-3, 0, 4)
Solid {
  translation -3 0.1 4
  children [
    Shape {
      appearance Appearance {
        material Material { diffuseColor 0 0 1 }  # Blue
      }
      geometry Sphere { radius 0.2 }
    }
  ]
}

# HOUSE_D marker (-2, 0, -3)
Solid {
  translation -2 0.1 -3
  children [
    Shape {
      appearance Appearance {
        material Material { diffuseColor 1 1 0 }  # Yellow
      }
      geometry Sphere { radius 0.2 }
    }
  ]
}

# HOME marker (0, 0, 0)
Solid {
  translation 0 0.1 0
  children [
    Shape {
      appearance Appearance {
        material Material { diffuseColor 1 0.5 0 }  # Orange
      }
      geometry Sphere { radius 0.3 }
    }
  ]
}
```

### 3. Set Robot Controller

In the hexapod robot node:

```
Robot {
  ...
  controller "main_hexapod_delivery"  # Use this controller
  ...
}
```

### 4. World Environment Setup

Ensure your world has:

```
# Flat ground
Floor {
  size 20 20  # Large enough for delivery routes
  appearance Appearance {
    material Material {
      diffuseColor 0.3 0.7 0.3  # Green grass
    }
  }
}

# Sky (optional)
Sky {
  luminosity 1
  skyColor 0.5 0.8 1  # Light blue
}

# Lighting
PointLight {
  intensity 1
  ambientIntensity 0.6
  location 5 5 5
}
```

### 5. Add Display Device (Optional)

For on-screen UI panel:

```
Display {
  name "display"
  width 400
  height 400
}
```

## 📋 Complete Example Robot Definition

```
DEF HEXAPOD Robot {
  translation 0 0.3 0
  rotation 0 1 0 0
  
  children [
    # Robot body and legs (your existing hexapod structure)
    
    # Sensors for delivery system
    GPS {
      name "gps"
      accuracy 0.01
    }
    Compass {
      name "compass"
      accuracy 0.01
    }
    InertialUnit {
      name "imu"
    }
    
    # Distance sensors
    DistanceSensor {
      translation 0.2 0 0
      rotation 0 1 0 0
      name "ds_front"
      lookupTable [0 1000 0, 0.5 0 0]
      type "sonar"
    }
    DistanceSensor {
      translation 0 0 0.2
      rotation 0 1 0 1.5708
      name "ds_left"
      lookupTable [0 1000 0, 0.5 0 0]
      type "sonar"
    }
    DistanceSensor {
      translation 0 0 -0.2
      rotation 0 1 0 -1.5708
      name "ds_right"
      lookupTable [0 1000 0, 0.5 0 0]
      type "sonar"
    }
    
    # Optional display for UI
    Display {
      name "display"
      width 400
      height 400
    }
  ]
  
  # Motor definitions (your existing motors)
  # Hip motors, knee motors, etc.
  
  controller "main_hexapod_delivery"
  controllerArgs []
  supervisor TRUE
}
```

## 🔧 Troubleshooting Sensor Issues

### GPS not working
- ✅ Ensure GPS sensor has `name "gps"`
- ✅ Check accuracy is not too low (e.g., 0.01 is reasonable)
- ✅ Verify robot starts above ground (y > 0.2)

### Compass not working
- ✅ Add compass with `name "compass"`
- ✅ Ensure accuracy is positive

### Distance sensors not detecting
- ✅ Check `lookupTable` values are reasonable
- ✅ Position sensors pointing outward from robot
- ✅ Use `type "sonar"` or `type "infrared"`
- ✅ Verify range limits (usually 0-0.5m for close range)

### Robot sinks through ground
- ✅ Increase `damping` in robot/world physics
- ✅ Check collision geometry is defined
- ✅ Verify contact properties between robot and floor

## 📍 Modifying Delivery Locations

If you change delivery points in world, update `config.py`:

```python
DELIVERY_LOCATIONS = {
    "HOME": (0.0, 0.0),
    "HOUSE_A": (3.0, 2.0),      # Update X, Z coordinates
    "HOUSE_B": (5.0, 5.0),      # matching world file
    "HOUSE_C": (-3.0, 4.0),
    "HOUSE_D": (-2.0, -3.0),
}
```

**Note**: World coordinates are (X, Y, Z) where:
- X = left/right
- Y = up/down (ignore for 2D navigation)
- Z = forward/backward

Use only (X, Z) for navigation.

## 🎨 Visual Markers for Delivery Points

Optional: Add colored markers at each delivery location:

```
# In world file, add at each delivery point:

Solid {
  translation X 0.15 Z          # X, Z from DELIVERY_POINTS
  children [
    Shape {
      appearance Appearance {
        material Material { 
          diffuseColor R G B     # RGB color
        }
      }
      geometry Sphere { radius 0.15 }
    }
  ]
  name "LOCATION_NAME"
  boundingObject Sphere { radius 0.15 }
  physics Physics {}
}
```

Color suggestions:
- HOME (0, 0, 0): Orange (1, 0.5, 0)
- HOUSE_A: Red (1, 0, 0)
- HOUSE_B: Green (0, 1, 0)
- HOUSE_C: Blue (0, 0, 1)
- HOUSE_D: Yellow (1, 1, 0)

## ✅ Pre-Flight Checklist

Before running simulation:

- [ ] GPS sensor added with name "gps"
- [ ] Compass sensor added with name "compass"
- [ ] Distance sensors added (ds_front, ds_left, ds_right, ds_back)
- [ ] IMU sensor present
- [ ] Controller set to "main_hexapod_delivery"
- [ ] World is flat and large enough (20x20m recommended)
- [ ] Delivery location markers visible (optional)
- [ ] Config.py matches world coordinates
- [ ] Robot starts above ground level

## 🚀 Testing

1. Open hexapod.wbt in Webots
2. Start simulation (play button)
3. Console should show startup messages
4. Robot stands up (takes ~2 seconds)
5. Press `S` key to start deliveries
6. Robot walks and navigates
7. Check console for status updates

## 📊 Performance Tips

- **Larger world**: Delivery routes optimize better
- **Flat terrain**: Robot walks faster and more stable
- **Good lighting**: Helps with visual debugging
- **Close sensors**: Better obstacle detection (0.5m range)
- **High timestep**: Faster simulation (8ms is default)

---

**World File Compatibility**: Webots 2022 R2+  
**Robot Type**: Hexapod (6-legged)  
**Controller**: Python 3.x
