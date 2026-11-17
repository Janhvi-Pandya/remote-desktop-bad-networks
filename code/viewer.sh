#!/bin/bash
# viewer.sh: opens the VNC viewer from inside the client namespace.
# Run it with:  ./viewer.sh   (it asks for your sudo password if needed)
# DISPLAY=:0 is WSL's display, so the window shows up on your Windows screen.
sudo ip netns exec client sudo -u "$USER" env DISPLAY=:0 vncviewer 10.0.0.1:1
