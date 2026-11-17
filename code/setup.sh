#!/bin/bash
# setup.sh: builds the whole testbed in one go.
# Run it with:  sudo ./setup.sh
# Safe to run again any time (for example after WSL restarts): it cleans up first.

set -e                                   # stop at the first command that fails

ME="${SUDO_USER:-$(whoami)}"             # your normal username (janhvi), even though the script runs with sudo
HOME_DIR=$(getent passwd "$ME" | cut -d: -f6)   # your home folder, e.g. /home/janhvi

echo "== 1. Cleaning up anything left from last time =="
pkill Xvnc 2>/dev/null || true           # stop an old VNC server if one is running ("|| true" = don't fail if none)
sleep 1
rm -f /tmp/.X1-lock                      # remove the old display lock file
ip netns del server 2>/dev/null || true  # delete old namespaces (this also deletes the cable ends inside them)
ip netns del client 2>/dev/null || true

echo "== 2. Building the two namespaces and the virtual cable =="
ip netns add server                      # apartment 1
ip netns add client                      # apartment 2
ip link add veth-s type veth peer name veth-c    # the virtual cable, ends veth-s and veth-c
ip link set veth-s netns server          # one end into each apartment
ip link set veth-c netns client
ip netns exec server ip addr add 10.0.0.1/24 dev veth-s   # server address
ip netns exec client ip addr add 10.0.0.2/24 dev veth-c   # client address
ip netns exec server ip link set veth-s up                # switch the ends on
ip netns exec client ip link set veth-c up
ip netns exec server ip link set lo up                    # switch on loopback in each
ip netns exec client ip link set lo up

echo "== 3. Checking the cable works (3 pings) =="
ip netns exec client ping -c 3 -q 10.0.0.1                # -q = only print the summary

echo "== 4. Starting the VNC server inside the server namespace =="
# Same Xvnc command as before, run as you (not root), messages go to ~/xvnc.log
# -SecurityTypes None = no VNC password. Safe here: port 5901 only exists inside the private namespaces.
# "setsid -f" starts it in its own separate session, so it keeps running after this script ends.
# Without it, sudo kills everything this script started in the background the moment the script exits.
setsid -f ip netns exec server sudo -u "$ME" Xvnc :1 -rfbport 5901 -localhost no \
    -SecurityTypes None -geometry 1280x720 \
    -nolisten unix -listen tcp > "$HOME_DIR/xvnc.log" 2>&1
sleep 2                                                   # give it a moment to start

echo "== 5. Starting the Xfce desktop on that VNC display =="
setsid -f ip netns exec server sudo -u "$ME" env DISPLAY=127.0.0.1:1 \
    dbus-launch startxfce4 > "$HOME_DIR/xfce.log" 2>&1
sleep 3

echo "== 6. Final check: is the VNC server answering? =="
GREETING=$(ip netns exec client sh -c 'timeout 2 nc 10.0.0.1 5901 | head -c 12')
if [ "$GREETING" = "RFB 003.008" ]; then
    echo "OK: server says $GREETING. Now run ./viewer.sh"
    sleep 3                                       # wait a little and check again, to be sure it stays up
    if ip netns exec server ss -tln | grep -q ":5901"; then
        echo "OK: still running after 3 seconds."
    else
        echo "PROBLEM: VNC server stopped after starting. Look at: tail $HOME_DIR/xvnc.log"
        exit 1
    fi
else
    echo "PROBLEM: no VNC greeting. Look at: tail $HOME_DIR/xvnc.log"
    exit 1
fi
