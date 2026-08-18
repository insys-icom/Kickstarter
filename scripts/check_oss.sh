#/bin/sh

# use wget to check for an updated packet
wget_check() {
    wget "$2" -q -O - | grep -qzoP "$3"
    [ "$?" != 0 ] && echo -en "$1: new version available on $2\n"
}

# wget_check <URL to check> <text to parse in the retrieved HTML>  <additional wget parameter>
wget_check "asyncinotify" "https://pypi.org/project/asyncinotify"                 "asyncinotify 4.4.4"
wget_check "busybox"      "https://busybox.net"                                   "</li>\n\n  <li><b>13 May 2026 -- BusyBox 1.38.0"
wget_check "cacert"       "https://curl.se/docs/caextract.html"                   "Tue Dec 2 04:12:02 2025 GMT"
wget_check "charset"      "https://pypi.org/project/charset-normalizer"           "charset-normalizer-3.5.1"
wget_check "cJSON"        "https://github.com/DaveGamble/cJSON"                   "1.7.19</span>"
wget_check "dropbear"     "https://matt.ucc.asn.au/dropbear/dropbear.html"        "Latest is 2026.94"
wget_check "idna"         "https://pypi.org/project/idna"                         "idna 3.18"
wget_check "libffi"       "https://github.com/libffi/libffi"                      "v3.8.0"
# libwebsockets 4.5.8
wget_check "libxcrypt"    "https://github.com/besser82/libxcrypt"                 ">v4.5.2</span>"
wget_check "metalog"      "https://github.com/hvisage/metalog"                    ">metalog-20260811</span>"
wget_check "mosquitto"    "https://mosquitto.org/download"                        "mosquitto-2.1.2.tar.gz"
# mqtt 5.15.2
wget_check "openssl"      "https://www.openssl.org/source"                        "openssl-3.6.3.tar.gz"
wget_check "paho.mqtt"    "https://github.com/eclipse-paho/paho.mqtt.python"      "v2.1.0"
wget_check "pcre2"        "https://github.com/PhilipHazel/pcre2"                  ">PCRE2 10.47</span>"
wget_check "python"       "https://docs.python.org/3/"                            "Python 3.14.7 documentation"
wget_check "jsonpath"     "https://pypi.org/project/python-jsonpath"              "python_jsonpath-2.2.1.tar.gz"
wget_check "radvd"        "https://radvd.litech.org"                              "2026/05/25: Release v2.21"
wget_check "requests"     "https://pypi.org/project/requests"                     "requests-2.34.2"
wget_check "timezone"     "https://www.iana.org/time-zones"                       "2026c"
wget_check "urllib3"      "https://pypi.org/project/urllib3"                      "urllib3 2.7.0"
wget_check "zlib"         "https://www.zlib.net"                                  "zlib 1.3"
