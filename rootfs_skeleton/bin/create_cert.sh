#!/bin/sh

PATH=$PATH:/bin

if ! [ -e /etc/ssl/ca_cert.pem ] ; then
    touch /etc/ssl/openssl.cnf

    # create self signed CA
    openssl req -x509 -newkey ec \
        -pkeyopt ec_paramgen_curve:prime256v1 \
        -keyout /etc/ssl/ca_key.pem \
        -out /etc/ssl/ca_cert.pem \
        -sha256 \
        -not_before 19700101000000Z \
        -not_after 99991231235959Z \
        -nodes \
        -subj "/C=DE/ST=Bayern/L=Regensburg/O=INSYS icom GmbH/CN=Kickstarter CA"

    # create certificate for HTTP
    openssl req -x509 -newkey ec \
        -pkeyopt ec_paramgen_curve:prime256v1 \
        -keyout /etc/httpd/key.pem \
        -out /etc/httpd/cert.pem \
        -sha256 \
        -not_before 19700101000000Z \
        -not_after 99991231235959Z \
        -nodes \
        -CA /etc/ssl/ca_cert.pem \
        -CAkey /etc/ssl/ca_key.pem \
        -subj "/C=DE/ST=Bayern/L=Regensburg/O=INSYS icom GmbH/CN=Kickstarter HTTPS"

    # create certificate for mosquitto
    openssl req -x509 -newkey ec \
        -pkeyopt ec_paramgen_curve:prime256v1 \
        -keyout /etc/mosquitto/key.pem \
        -out /etc/mosquitto/cert.pem \
        -sha256 \
        -not_before 19700101000000Z \
        -not_after 99991231235959Z \
        -nodes \
        -CA /etc/ssl/ca_cert.pem \
        -CAkey /etc/ssl/ca_key.pem \
        -subj "/C=DE/ST=Bayern/L=Regensburg/O=INSYS icom GmbH/CN=Kickstarter MQTT"
fi
