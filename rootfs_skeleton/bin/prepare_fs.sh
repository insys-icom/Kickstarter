#!/bin/sh

# enable forwarding to silence radvd
echo 1 > /proc/sys/net/ipv6/conf/all/forwarding

[ -e /data/etc/kickstarter.json ] || cp /root/kickstarter/config_template.json /data/etc/kickstarter.json
[ -e /data/etc/httpd.conf ] || touch /data/etc/httpd.conf
[ -e /data/etc/shadow ] || cp /etc/shadow_default /data/etc/shadow && ln -s /data/etc/shadow /etc/shadow

/bin/mkdir -p /tmp/lock /tmp/run /data/kickstarter /data/log /data/kickstarter/files /data/kickstarter/hashes /data/kickstarter/irm /data/kickstarter/ics
ln -s /data/log /var/log
