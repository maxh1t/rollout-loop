#!/bin/bash
# Sources the ROS + workspace overlay, then execs whatever CMD (or a docker
# run/exec override) was passed — shared by the app container, the
# foxglove_bridge container, and the in-container health check, so all three
# get an identical environment.
set -e
source /opt/ros/jazzy/setup.bash
source /workspace/install/setup.bash
exec "$@"
