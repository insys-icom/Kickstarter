#!/bin/sh
scp -O app/*.py user@192.168.1.11:kickstarter/
scp -Or web/* root@192.168.1.11:/var/web/
