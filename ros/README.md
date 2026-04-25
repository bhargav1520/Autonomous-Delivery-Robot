# ROS + Webots Robot Workflow

This document explains how your robot delivery system works in:
1. Webots (current main simulation)
2. ROS 2 (current ROS folder implementation)
3. How both parts map to each other

## 1) Webots Side (Main Project Flow)

Your primary robot logic is currently implemented for Webots as a hexapod.

Key files:
- controllers/hexapod/main_hexapod_delivery.py
- controllers/hexapod/delivery_system.py
- controllers/hexapod/ui_control.py
- worlds/hexapod.wbt

### Webots Control Architecture

The main controller (main_hexapod_delivery.py) runs a control loop that does:
1. Reads keyboard commands from UI (start route, status, stop)
2. Updates the delivery state machine
3. Applies gait commands to 6 legs
4. Uses sensors for navigation and obstacle handling

The delivery system (delivery_system.py) handles:
- State machine: IDLE, NAVIGATING, DELIVERING, RETURNING
- Route planning: nearest-neighbor path over delivery points
- Navigation: GPS + compass based waypoint checks
- Obstacle logic: front/left/right/back clearance and escape direction
- Battery simulation: drain, low-battery return, recharge at HOME

### Webots Delivery Behavior

Typical full cycle:
1. Robot starts at HOME
2. Route is planned over selected houses
3. Robot walks using tripod gait while navigating to each target
4. At each location, robot stops for DELIVERY_STOP_TIME
5. After all targets, robot returns HOME
6. Battery is restored at HOME and system returns to IDLE

## 2) ROS 2 Side (Current ros Folder)

Your ros folder contains a ROS 2 + Gazebo implementation of a quadruped-style delivery demo.

Files:
- ros/delivery_node.py
- ros/gazebo.launch.py
- ros/delivery_world.world

### What the ROS Node Does

delivery_node.py creates a node named delivery_node and:
- Subscribes to /odom (robot position + orientation)
- Publishes movement commands on /cmd_vel
- Publishes leg animation on /joint_states
- Calls /set_entity_state service to move delivery_box

State sequence in ROS node:
1. PICK: navigate to PICKUP_POINT (2.0, 2.0)
2. On close range (< 0.15 m), switch to DROP and mark carrying = True
3. While carrying, keep delivery_box above robot
4. DROP: navigate to DROP_POINT (-2.0, -2.0)
5. After minimum carry time and near target, drop box and set DONE

### What the ROS Launch File Does

gazebo.launch.py:
1. Loads package share directory for quadruped_delivery
2. Builds robot_description from urdf/quadruped.urdf.xacro
3. Starts Gazebo with worlds/delivery_world.world
4. Starts robot_state_publisher
5. Spawns robot entity in Gazebo
6. Publishes static transform base_link -> base_footprint

## 3) Webots vs ROS in This Repository

Important clarification:
- Webots implementation is the main and more complete autonomous delivery system (hexapod).
- ros folder currently targets Gazebo, not Webots runtime integration.

So right now you have:
- Full Webots controller stack in controllers/hexapod
- Separate ROS/Gazebo demo in ros

## 4) How to Run

### Run Webots System
1. Open worlds/hexapod.wbt in Webots
2. Ensure robot controller is set to main_hexapod_delivery
3. Start simulation
4. Use keyboard controls from ui_control.py (for example: start, status, stop)

### Run ROS 2 Gazebo Demo
Prerequisites:
- ROS 2 installed (Humble or compatible)
- gazebo_ros, robot_state_publisher, tf2_ros installed
- A valid ROS 2 package named quadruped_delivery with:
  - urdf/quadruped.urdf.xacro
  - worlds/delivery_world.world
  - launch/gazebo.launch.py
  - delivery_node.py installed as executable

Example commands:
1. Build workspace: colcon build
2. Source setup: source install/setup.bash
3. Launch world + robot: ros2 launch quadruped_delivery gazebo.launch.py
4. Run node (if not auto-launched): ros2 run quadruped_delivery delivery_node

## 5) Topic and Interface Summary (ROS)

Published:
- /cmd_vel (geometry_msgs/Twist)
- /joint_states (sensor_msgs/JointState)

Subscribed:
- /odom (nav_msgs/Odometry)

Service client:
- /set_entity_state (gazebo_msgs/SetEntityState)

## 6) Recommended Next Step (If You Want ROS + Webots Together)

If your goal is ROS + Webots integration (instead of Gazebo), migrate the ROS node to Webots interfaces:
1. Use Webots ROS 2 bridge (webots_ros2)
2. Replace Gazebo-specific service /set_entity_state with Webots-compatible object control
3. Map Webots sensors (GPS/IMU/compass/distance sensors) to ROS topics
4. Keep delivery state machine in ROS node, use Webots only for simulation and physics

This gives one ROS control layer with Webots visualization and simulation.

---
Last updated: April 25, 2026
