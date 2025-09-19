#!/bin/bash

DESCRIPTION="Container running the Kickstarter"
CONTAINER_NAME="container_kickstarter"
ROOTFS_LIST="rootfs_list_kickstarter.txt"

PACKAGES_1=(
    "libxcrypt-4.4.38.sh"
    "cacert-2025-09-09.sh"
    "zlib-1.3.sh"
    "tzdb-2025b.sh"
)
PACKAGES_2=(
    "lz4-1.10.0.sh"
    "pcre2-10.46.sh"
    "openssl-3.5.2.sh"
    "libffi-3.5.2.sh"
    "certifi.sh"
    "charset-normalizer-3.4.3.sh"
    "idna-3.10.sh"
    "requests-2.32.5.sh"
    "urllib3-2.5.0.sh"
    "paho.mqtt.eclipse-2.1.0.sh"
    "python_jsonpath-1.3.2.sh"
    "cJSON-1.7.18.sh"
    "asyncinotify-4.2.1.sh"
    "mqtt-5.10.0.min.js.sh"
)
PACKAGES_3=(
    "busybox-1.36.1.sh"
    "dropbear-2025.88.sh"
    "metalog-20230719.sh"
    "radvd-2.19.sh"
    "libwebsockets-4.3.3.sh"
)
PACKAGES_4=(
    "mosquitto-2.0.22.sh"
    "python-3.13.7.sh"
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
