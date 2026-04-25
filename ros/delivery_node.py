#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from sensor_msgs.msg import JointState
from gazebo_msgs.srv import SetEntityState
from gazebo_msgs.msg import EntityState
import math
import time

PICKUP_POINT = (2.0, 2.0)
DROP_POINT   = (-2.0, -2.0)

class DeliveryNode(Node):
    def __init__(self):
        super().__init__('delivery_node')

        self.cmd_pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self.joint_pub = self.create_publisher(JointState, '/joint_states', 10)

        self.create_subscription(Odometry, '/odom', self.odom_cb, 10)

        self.cli = self.create_client(SetEntityState, '/set_entity_state')

        self.timer = self.create_timer(0.05, self.loop)
        self.anim_timer = self.create_timer(0.03, self.animate)

        self.x = 0.0
        self.y = 0.0
        self.yaw = 0.0

        self.goal = PICKUP_POINT
        self.state = "PICK"
        self.carrying = False

        self.pick_time = None  # for delay
        self.t = 0.0

    def odom_cb(self, msg):
        self.x = msg.pose.pose.position.x
        self.y = msg.pose.pose.position.y

        q = msg.pose.pose.orientation
        siny = 2*(q.w*q.z + q.x*q.y)
        cosy = 1 - 2*(q.y*q.y + q.z*q.z)
        self.yaw = math.atan2(siny, cosy)

    def move_box(self, x, y, z):
        if not self.cli.service_is_ready():
            return

        req = SetEntityState.Request()
        req.state = EntityState()
        req.state.name = "delivery_box"

        req.state.pose.position.x = x
        req.state.pose.position.y = y
        req.state.pose.position.z = z
        req.state.pose.orientation.w = 1.0

        self.cli.call_async(req)

    def loop(self):
        dx = self.goal[0] - self.x
        dy = self.goal[1] - self.y
        dist = math.hypot(dx, dy)

        angle = math.atan2(dy, dx)
        err = angle - self.yaw

        while err > math.pi: err -= 2*math.pi
        while err < -math.pi: err += 2*math.pi

        cmd = Twist()

        # 🔴 PICKUP ONLY WHEN VERY CLOSE
        if dist < 0.15 and self.state == "PICK":
            self.get_logger().info("PICKED")
            self.carrying = True
            self.state = "DROP"
            self.goal = DROP_POINT
            self.pick_time = time.time()

        # 🟢 CARRY BOX ABOVE ROBOT
        if self.carrying:
            self.move_box(self.x, self.y, 0.5)

        # 🔵 DROP ONLY AFTER MOVING FOR SOME TIME
        if self.carrying and self.state == "DROP":
            if time.time() - self.pick_time > 4.0 and dist < 0.4:
                self.get_logger().info("DROPPED")
                self.move_box(self.x, self.y, 0.2)
                self.carrying = False
                self.state = "DONE"

        # 🟡 MOVEMENT
        if abs(err) > 0.2:
            cmd.angular.z = 2.5 * err
        else:
            cmd.linear.x = 1.2

        self.cmd_pub.publish(cmd)

    def animate(self):
        js = JointState()
        js.header.stamp = self.get_clock().now().to_msg()

        names = []
        pos = []

        legs = ['fl','fr','rl','rr']
        for i, leg in enumerate(legs):
            phase = (self.t + i*0.5) % 1.0

            # smooth walking motion
            hip = 0.4 * math.sin(2*math.pi*phase)
            knee = -0.6 + 0.4 * max(0, math.sin(2*math.pi*phase))

            names += [f"{leg}_hip_joint", f"{leg}_knee_joint"]
            pos += [hip, knee]

        js.name = names
        js.position = pos

        self.joint_pub.publish(js)
        self.t += 0.03


def main():
    rclpy.init()
    node = DeliveryNode()
    rclpy.spin(node)
    rclpy.shutdown()

if __name__ == "__main__":
    main()