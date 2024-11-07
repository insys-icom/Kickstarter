#/bin/sh

# use wget to check for an updated packet
wget_check() {
    wget "$2" "$4" -q -O - | grep -qzoP "$3"
    [ "$?" != 0 ] && echo -en "$1: new version available on $2\n"
}

# wget_check <URL to check> <text to parse in the retrieved HTML>  <additional wget parameter>
wget_check "lz4"          "https://github.com/lz4/lz4"                            ">LZ4 v1.10.0" ""
wget_check "openssl"      "https://www.openssl.org/source"                        "openssl-3.4.0.tar.gz" ""
wget_check "pcre2"        "https://github.com/PhilipHazel/pcre2"                  ">PCRE2-10.44</span>" ""
wget_check "timezone"     "https://www.iana.org/time-zones"                       "Released 2024-09-04" ""
wget_check "zlib"         "https://www.zlib.net"                                  "zlib 1.3" ""
wget_check "busybox"      "https://busybox.net"                                   "</li>\n\n  <li><b>19 May 2023 -- BusyBox 1.36.1" ""
wget_check "metalog"      "https://github.com/hvisage/metalog"                    ">metalog-20230719</span>" ""
wget_check "cacert"       "https://curl.se/docs/caextract.html"                   "Tue Sep 24 03:12:04 2024 GMT" ""
wget_check "dropbear"     "https://matt.ucc.asn.au/dropbear/dropbear.html"        "Latest is 2024.86" ""
wget_check "python"       "https://docs.python.org/3/"                            "Python 3.13.0 documentation" ""
wget_check "cJSON"        "https://github.com/DaveGamble/cJSON"                   "1.7.18</span>" ""
wget_check "mosquitto"    "https://mosquitto.org/download"                        "mosquitto-2.0.20.tar.gz" ""
wget_check "asyncinotify" "https://pypi.org/project/asyncinotify"                 "asyncinotify 4.2.0" ""
wget_check "charset"      "https://pypi.org/project/charset-normalizer"           "charset-normalizer-3.4.0" ""
wget_check "idna"         "https://pypi.org/project/idna"                         "idna-3.10" ""
wget_check "requests"     "https://pypi.org/project/requests"                     "requests-2.32.3" ""
wget_check "urllib3"      "https://pypi.org/project/urllib3"                      "urllib3 2.2.3" ""

# wget_check "screen"     "https://ftp.gnu.org/gnu/screen"                        "screen-4.9.0.tar.gz.sig</a></td><td align=\"right\">2022-02-01 11:01  </td><td align=\"right\">659 </td><td>&nbsp;</td></tr>\n   <tr><th" ""
