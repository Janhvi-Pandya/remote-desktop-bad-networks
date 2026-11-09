#!/bin/bash
# sweep.sh: runs all the single-condition tests one after another.
# Usage:  ./sweep.sh 100      (100 trials per condition; default 100)
# Before running: setup.sh done and flip.py running in the remote desktop (the viewer is optional).
# It will ask for your sudo password once (needed to change netem).

TRIALS=${1:-100}

run () {                         # run LABEL then the net.sh arguments
  LABEL=$1; shift
  sudo ./net.sh "$@" > /dev/null # set the network condition on both ends
  sleep 2                        # let things settle after the change
  sudo ip netns exec client python3 measure.py "$LABEL" "$TRIALS"   # measure from inside the client namespace
}

sudo -v                          # ask for the sudo password now, so it doesn't interrupt later

run base       off
run delay25    delay 25          # 25 ms each way = about 50 ms round trip
run delay50    delay 50
run delay100   delay 100
run delay150   delay 150
run loss1      loss 1            # 1% loss each way
run loss2      loss 2
run loss5      loss 5
run loss10     loss 10

sudo ./net.sh off > /dev/null    # leave the network perfect when done
sudo chown -R "$USER" results     # results were written as root; give the files back to you
echo "All done. Results are in the results/ folder."
