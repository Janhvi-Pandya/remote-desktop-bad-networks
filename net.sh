#!/bin/bash
# net.sh: changes the "network quality" on BOTH ends of the cable at once.
# Usage (always with sudo):
#   sudo ./net.sh delay 100      -> 100 ms each way (about 200 ms ping)
#   sudo ./net.sh loss 2         -> 2% loss each way
#   sudo ./net.sh both 50 2      -> 50 ms delay AND 2% loss each way
#   sudo ./net.sh off            -> perfect network again
#   sudo ./net.sh show           -> print what is active right now

case "$1" in
  delay) RULE="delay ${2}ms" ;;              # build the netem rule text from your numbers
  loss)  RULE="loss ${2}%" ;;
  both)  RULE="delay ${2}ms loss ${3}%" ;;
  off)
    ip netns exec server tc qdisc del dev veth-s root 2>/dev/null   # remove netem (no error if none)
    ip netns exec client tc qdisc del dev veth-c root 2>/dev/null
    echo "network is perfect again"
    exit 0 ;;
  show)
    echo "server end:"; ip netns exec server tc qdisc show dev veth-s
    echo "client end:"; ip netns exec client tc qdisc show dev veth-c
    exit 0 ;;
  *)
    echo "usage: sudo ./net.sh delay MS | loss PCT | both MS PCT | off | show"
    exit 1 ;;
esac

# "replace" = add the rule, or swap out whatever rule was there before
ip netns exec server tc qdisc replace dev veth-s root netem $RULE
ip netns exec client tc qdisc replace dev veth-c root netem $RULE
echo "applied on both ends: $RULE"
