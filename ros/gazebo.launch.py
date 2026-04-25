import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
import xacro

def generate_launch_description():
    pkg        = get_package_share_directory('quadruped_delivery')
    gazebo_ros = get_package_share_directory('gazebo_ros')

    xacro_file         = os.path.join(pkg, 'urdf',   'quadruped.urdf.xacro')
    world_file         = os.path.join(pkg, 'worlds', 'delivery_world.world')
    robot_description  = xacro.process_file(xacro_file).toxml()

    return LaunchDescription([

        # Gazebo with our world
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(gazebo_ros, 'launch', 'gazebo.launch.py')
            ),
            launch_arguments={'world': world_file, 'verbose': 'false'}.items()
        ),

        # Robot state publisher
        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            parameters=[{'robot_description': robot_description,
                         'use_sim_time': True}],
            output='screen'
        ),

        # Spawn robot at origin slightly above ground
        Node(
            package='gazebo_ros',
            executable='spawn_entity.py',
            arguments=[
                '-topic', 'robot_description',
                '-entity', 'quadruped',
                '-x', '0.0',
                '-y', '0.0',
                '-z', '0.22',   # just above ground so legs touch
                '-R', '0.0',
                '-P', '0.0',
                '-Y', '0.0',
            ],
            output='screen'
        ),

        # Static transform: base_link -> base_footprint
        Node(
            package='tf2_ros',
            executable='static_transform_publisher',
            arguments=['0', '0', '0', '0', '0', '0', 'base_link', 'base_footprint'],
            output='screen'
        ),
    ])
