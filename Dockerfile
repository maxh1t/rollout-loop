# Runtime image for the `detector` package (MAX-10 / P4). Single-stage:
# colcon build for an ament_python package is cheap (no C++ compilation), so
# a build/runtime split buys little here and just adds a second stage to
# keep in sync.
FROM ros:jazzy-ros-base

WORKDIR /workspace
COPY src/detector src/detector

# cv_bridge's apt package transitively pulls in a full desktop-enabled
# OpenCV/GStreamer/Qt/GTK stack on Ubuntu — none of it reachable in a
# headless container. Most of it is apt Recommends, not hard Depends, so
# disabling Recommends globally (picked up by rosdep's own apt-get calls
# too, not just the explicit install below) trims it substantially.
RUN echo 'APT::Install-Recommends "0";' > /etc/apt/apt.conf.d/99no-recommends

# rosdep resolves everything package.xml declares (vision_msgs, cv_bridge,
# python3-opencv, image_transport, launch, launch_ros, std_srvs, ...).
# foxglove_bridge and compressed_image_transport aren't `detector`'s own
# deps (they're the separate tools the launch file / remote-viewing setup
# rely on, per README) so they're installed explicitly alongside.
RUN apt-get update && \
    rosdep update && \
    rosdep install --from-paths src --ignore-src -r -y && \
    apt-get install -y --no-install-recommends \
      python3-pip \
      ros-jazzy-foxglove-bridge \
      ros-jazzy-compressed-image-transport && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# onnxruntime has no apt/rosdep key for its Python bindings on this platform
# (see README) — only a pip install works. ros:jazzy-ros-base has no pip
# preinstalled, hence python3-pip above.
RUN pip3 install --break-system-packages --no-cache-dir onnxruntime

RUN /bin/bash -c "source /opt/ros/jazzy/setup.bash && colcon build"

# Baked in from the CI commit (see .github/workflows/build.yml), not read
# from .git at runtime -- there is no .git in this image (only src/detector
# is COPYed above) and colcon's install step copies files out of the git
# working tree regardless. Placed this late so changing it on every commit
# doesn't invalidate the expensive layers above.
ARG GIT_SHA=unknown
ENV CODE_VERSION=$GIT_SHA

# Runs inside the running container as the device-side health signal for
# the deploy pipeline (MAX-10) — invoked via `docker exec`, not started on
# its own, so it isn't part of the default CMD below.
COPY deploy/healthcheck.py /workspace/healthcheck.py

COPY deploy/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["ros2", "launch", "detector", "pipeline.launch.py", "source:=0", "compressed:=true"]
