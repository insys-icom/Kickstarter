#!/bin/bash

DESCRIPTION="Container running the Kickstarter"
CONTAINER_NAME="container_kickstarter"
ROOTFS_LIST="rootfs_list_kickstarter.txt"

PACKAGES_1=(
    "libxcrypt-4.4.38.sh"
    "cacert-2024-11-26.sh"
    "zlib-1.3.sh"
    "tzdb-2024b.sh"
)
PACKAGES_2=(
    "lz4-1.10.0.sh"
    "pcre2-10.44.sh"
    "openssl-3.4.0.sh"
    "libffi-3.4.6.sh"
    "certifi.sh"
    "charset-normalizer-3.4.0.sh"
    "idna-3.10.sh"
    "requests-2.32.3.sh"
    "urllib3-2.2.3.sh"
    "paho.mqtt.eclipse-2.1.0.sh"
    "cJSON-1.7.18.sh"
    "asyncinotify-4.2.0.sh"
    "mqtt-5.10.0.min.js.sh"

)
PACKAGES_3=(
    "busybox-1.36.1.sh"
    "dropbear-2024.86.sh"
    "metalog-20230719.sh"
    "radvd-2.19.sh"
    "libwebsockets-4.3.3.sh"
)
PACKAGES_4=(
    "mosquitto-2.0.20.sh"
    "python-3.13.1.sh"
)

PACKAGES=(
    PACKAGES_1[@]
    PACKAGES_2[@]
    PACKAGES_3[@]
    PACKAGES_4[@]
)

# in case $1 is "do_nothing" this script will end here
[ "$1" == "do_nothing" ] && return

. $(realpath $(dirname ${BASH_SOURCE[0]}))/create.sh "${@}"
