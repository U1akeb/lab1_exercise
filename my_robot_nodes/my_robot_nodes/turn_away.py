#!/usr/bin/env python3
"""Autonomous obstacle avoidance controller for diffdrive_bot.
Drives forward when the path is clear, turns away from obstacles, and supports
runtime parameter tuning and service-based enabling/disabling."""

import rclpy
from geometry_msgs.msg import Twist
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.parameter import Parameter
from std_srvs.srv import SetBool

from lab_interfaces.msg import ObstacleInfo
from my_robot_interfaces.msg import RobotStatus
from my_robot_interfaces.srv import SetTurnSpeed


class TurnAway(Node):

    def __init__(self):
        super().__init__("turn_away")

        # Declare configurable parameters
        self.declare_parameter("forward_speed", 0.2)
        self.declare_parameter("turn_speed", 0.5)
        self.declare_parameter("max_turn_speed", 1.5)

        # Starts disabled until /turn_away_enable service is called
        self.enabled = False

        # Publishers and subscribers
        self.cmd_vel_pub = self.create_publisher(Twist, "cmd_vel", 10)
        self.status_pub = self.create_publisher(RobotStatus, "robot_status", 10)
        self.create_subscription(ObstacleInfo, "obstacle", self.on_obstacle, 10)

        # Service servers
        self.create_service(SetBool, "turn_away_enable", self.on_enable)
        self.create_service(SetTurnSpeed, "set_turn_speed", self.on_set_turn_speed)

        self.get_logger().info("turn_away controller initialized (disabled by default)")

    def on_obstacle(self, msg: ObstacleInfo):
        # Read parameters dynamically each callback so parameter changes take immediate effect
        forward_speed = float(self.get_parameter("forward_speed").value)
        turn_speed = float(self.get_parameter("turn_speed").value)

        status_msg = RobotStatus()
        status_msg.obstacle_distance = float(msg.distance)

        # While switched off, publish state as stopped and send no movement commands
        if not self.enabled:
            status_msg.state = "stopped"
            self.status_pub.publish(status_msg)
            return

        twist = Twist()
        if not msg.too_close:
            # Clear forward path
            status_msg.state = "forward"
            twist.linear.x = forward_speed
            twist.angular.z = 0.0
        else:
            # Obstacle too close: turn on the spot away from it
            status_msg.state = "turning"
            twist.linear.x = 0.0
            # Positive angle means obstacle is to the left, so turn right (negative angular.z)
            if msg.angle > 0.0:
                twist.angular.z = -turn_speed
            else:
                twist.angular.z = turn_speed

        self.cmd_vel_pub.publish(twist)
        self.status_pub.publish(status_msg)

    def on_enable(self, request, response):
        if request.data:
            self.enabled = True
            response.success = True
            response.message = "turn_away controller enabled"
        else:
            self.enabled = False
            # Send a zero velocity twist to ensure the robot stops immediately
            self.cmd_vel_pub.publish(Twist())
            response.success = True
            response.message = "turn_away controller disabled and stopped"

        self.get_logger().info(response.message)
        return response

    def on_set_turn_speed(self, request, response):
        max_turn_speed = float(self.get_parameter("max_turn_speed").value)
        if not (0.0 < request.turn_speed <= max_turn_speed):
            response.success = False
            response.message = (
                f"turn_speed must be > 0 and <= {max_turn_speed:.2f} rad/s"
            )
        else:
            self.set_parameters([Parameter("turn_speed", value=float(request.turn_speed))])
            response.success = True
            response.message = f"turn_speed updated to {request.turn_speed:.2f} rad/s"

        self.get_logger().info(response.message)
        return response


def main():
    rclpy.init()
    node = TurnAway()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    node.destroy_node()
    rclpy.try_shutdown()


if __name__ == "__main__":
    main()
