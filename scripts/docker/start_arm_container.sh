#!/bin/bash
docker run -d \
    -p "8080:8080" \
    -v "<path_to_arm_user_home_folder>:/home/arm" \
    -v "<path_to_music_folder>:/home/arm/Music" \
    -v "<path_to_logs_folder>:/home/arm/logs" \
    -v "<path_to_media_folder>:/home/arm/media" \
    -v "<path_to_config_folder>:/etc/arm/config" \
    --privileged \
    --restart "always" \
    --name "arm-rippers" \
    ARM_UID \
    ARM_GID \
    CPUS \
    MOUNTS \
    IMAGE_NAME
