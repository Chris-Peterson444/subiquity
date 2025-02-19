#!/bin/bash
set -eux

if [ "$#" -lt 2 ]; then
    cat >&2 <<EOF
usage: $0 <lxd-image> <test-command>

positional arguments:
  lxd-image     the LXD image to launch
  test-command  the command to run on the container

example:
  $0 ubuntu-daily:noble "make check"
EOF
    exit 1
fi

IMAGE=$1
TEST_CMD=$2
TESTER=subiquity-${IMAGE##*:}

lxd init --auto

# If the runner image uses docker, then work around a known connectivity issue
# when using lxd and docker at the same time.
# https://discuss.linuxcontainers.org/t/containers-do-not-have-outgoing-internet-access/10844/7
# https://documentation.ubuntu.com/lxd/en/latest/howto/network_bridge_firewalld/#prevent-connectivity-issues-with-lxd-and-docker
if [ "active" == "$(systemctl is-active docker)" ]
then
    iptables  -I DOCKER-USER -i lxdbr0 -j ACCEPT
    iptables  -I DOCKER-USER -o lxdbr0 -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
    # GitHub doesn't use IPV6 (yet?)
    # ip6tables -I DOCKER-USER -i lxdbr0 -j ACCEPT
    # ip6tables -I DOCKER-USER -o lxdbr0 -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
fi


if [ -z "$(lxc list -f csv -c n ^${TESTER}\$)" ]
then
    # using security.nesting=true for LP: #2046486
    lxc launch $IMAGE $TESTER -c security.nesting=true
    lxc config device add $TESTER code disk source=`pwd` path=/subiquity
else
    lxc start $TESTER
fi
# copy is allowed to fail, in case the subiquity directory being tested
# includes some uncopyable stuff
lxc exec $TESTER -- sh -ec "
    cd ~
    sudo cp -a /subiquity . || true
    [ -d ~/subiquity ]
    "

attempts=0
while ! lxc file pull $TESTER/etc/resolv.conf - 2> /dev/null | grep -q ^nameserver; do
    sleep 1
    attempts=$((attempts+1))
    if [ $attempts -gt 30 ]; then
        lxc file pull $TESTER/etc/resolv.conf
        lxc exec $TESTER -- ps aux
        echo "Network failed to come up after 30 seconds"
        exit 1
    fi
done
if ! lxc file pull $TESTER/etc/resolv.conf - 2> /dev/null | grep ^nameserver | grep -qv 127.0.0.53
then
    echo "systemd-resolved"
    while ! lxc file pull $TESTER/run/systemd/resolve/resolv.conf - 2> /dev/null | grep -v fe80 | grep -q ^nameserver; do
        sleep 1
        attempts=$((attempts+1))
        if [ $attempts -gt 30 ]; then
            echo "Network failed to come up after 30 seconds"
            exit 1
        fi
    done
fi

if ! lxc exec $TESTER -- cloud-init status --wait; then
    ec=$?
    case $ec in
        0|2)
            # 2 is warnings
            ;;
        *)
            echo "cloud-init status failed with $ec"
            exit $ec
            ;;
    esac
fi

lxc exec $TESTER -- sh -ec "
    cd ~/subiquity
    ./scripts/installdeps.sh
    $TEST_CMD"

lxc stop $TESTER
