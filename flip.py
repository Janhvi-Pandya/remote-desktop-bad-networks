# flip.py: runs INSIDE the remote desktop (on the server side).
# It shows a full-screen grey window with a square in the middle.
# Every key press flips the square between black and white.
# The measuring script on the client side watches that square to see
# exactly when the key press has made it all the way to the screen and back.

import tkinter as tk

root = tk.Tk()                                   # create the window
root.attributes("-fullscreen", True)             # cover the whole remote screen (hides the panel)
canvas = tk.Canvas(root, bg="grey", highlightthickness=0)   # a blank drawing area
canvas.pack(fill="both", expand=True)            # make the drawing area fill the window

W, H = 1280, 720                                 # the remote screen size we set in Xvnc (-geometry)
SIZE = 100                                       # square is 100 x 100 pixels: a small update, like typing
x0, y0 = W // 2 - SIZE // 2, H // 2 - SIZE // 2  # top-left corner so the square sits in the centre
square = canvas.create_rectangle(x0, y0, x0 + SIZE, y0 + SIZE, fill="black", outline="")

is_black = True                                  # remember the current colour

def on_key(event):                               # runs every time any key is pressed
    global is_black
    is_black = not is_black                      # flip the remembered colour
    canvas.itemconfig(square, fill="black" if is_black else "white")   # repaint the square

root.bind("<Key>", on_key)                       # connect key presses to on_key
root.bind("<Escape>", lambda e: root.destroy())  # Esc closes the app
root.focus_force()                               # grab keyboard focus so key presses reach us
root.mainloop()                                  # wait for events forever
