#!/bin/bash

DESCRIPTION="Container running the Kickstarter"
CONTAINER_NAME="container_kickstarter"
ROOTFS_LIST="rootfs_list_kickstarter.txt"

PACKAGES_1=(
    "libxcrypt-4.5.2.sh"
    "cacert-2026-08-13.sh"
    "zlib-1.3.sh"
    "tzdb-2026c.sh"
)
PACKAGES_2=(
    "pcre2-10.47.sh"
    "openssl-3.6.3.sh"
    "libffi-3.8.0.sh"
    "certifi.sh"
    "charset-normalizer-3.5.1.sh"
    "idna-3.18.sh"
    "requests-2.34.2.sh"
    "urllib3-2.7.0.sh"
    "paho.mqtt.eclipse-2.1.0.sh"
    "python-jsonpath-2.2.1.sh"
    "cJSON-1.7.19.sh"
    "asyncinotify-4.4.4.sh"
    "mqtt-5.15.2.min.js.sh"
)
PACKAGES_3=(
    "busybox-1.38.0.sh"
    "dropbear-2026.94.sh"
    "metalog-20260811.sh"
    "radvd-2.21.sh"
    "libwebsockets-4.5.8.sh"
)
PACKAGES_4=(
    "mosquitto-2.1.2.sh"
    "python-3.14.7.sh"
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
