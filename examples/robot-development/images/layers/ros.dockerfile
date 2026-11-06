ENV ROS_DISTRO=jazzy

# Use the regular ROS repository, without snapshot sources or package pins.
RUN curl -fsSL -o /tmp/ros2-apt-source.deb \
        https://github.com/ros-infrastructure/ros-apt-source/releases/download/1.2.0/ros2-apt-source_1.2.0.noble_all.deb \
    && echo "0804d9b13db770eb87019be414cd78378835228ad5fa801fc88758596dd8f7e5  /tmp/ros2-apt-source.deb" | sha256sum --check \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        /tmp/ros2-apt-source.deb \
    && rm /tmp/ros2-apt-source.deb \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        python3-colcon-common-extensions \
        ros-jazzy-ros-base \
        ros-jazzy-navigation2 \
        ros-jazzy-nav2-bringup \
        ros-jazzy-nav2-minimal-tb3-sim \
        ros-jazzy-rviz2 \
    && rm -rf /var/lib/apt/lists/*
