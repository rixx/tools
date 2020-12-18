import csv
import shutil
import sys
import itertools
from io import StringIO
from tkinter import *
from tkinter import ttk
from tkinter import font
from PIL import Image, ImageTk
from pathlib import Path


root = Tk()
w, h = root.winfo_screenwidth(), root.winfo_screenheight()
root.title("Photo sorter")
root.geometry(f"{w}x{h}+0+0")
root.config(background="white")

path = Path(sys.argv[1]).expanduser().absolute()
destination = Path(sys.argv[2]).expanduser().absolute()

seen_images = []
if Path("seen_images.txt").exists():
    with open("seen_images.txt") as f:
        for line in f:
            seen_images.append(Path(line.strip()).absolute())
seen_images = list(set(seen_images))

all_extensions = {"jpg", "JPG", "png", "PNG", "jpeg", "JPEG"}
get_images = lambda x: path.glob(f"**/*.{x}")
all_images = list(
    f.absolute() for f in
    itertools.chain.from_iterable(list(get_images(extension)) for extension in all_extensions)
    if f.absolute() not in seen_images
)
total_images = len(all_images)
all_images = iter(all_images)

current_image = None
current_index = -1
total_saved = 0


def quit(*args, **kwargs):
    with open("seen_images.txt", "w") as f:
        f.write("\n".join([str(p) for p in seen_images]))
    sys.exit()


def go_to_next_image():
    global current_image, image_element, current_index
    if current_image:
        seen_images.append(current_image.absolute())
    try:
        while not current_image or current_image in seen_images:
            current_image = next(all_images)
            current_image = current_image.absolute()
    except StopIteration:
        print("We are done here! You selected {total_saved} out of {total_images} images.")
        sys.exit()

    current_index += 1
    progressbar["value"] = current_index + 1
    root.style.configure(
        "LabeledProgressbar", text=f"{current_index + 1} / {total_images}"
    )
    image = Image.open(current_image)
    if image.width > 1800 or image.height > 900:
        image.thumbnail((1800, 900))
    image_element = ImageTk.PhotoImage(image)
    canvas.itemconfig(image_id, image=image_element)

def move_image():
    global total_saved
    total_saved += 1
    basis = current_image.relative_to(path).parts
    year = basis[0]
    destdir = destination / year
    if not destdir.exists():
        destdir.mkdir()
    destloc = destdir / "_".join(basis[1:])
    shutil.copy(current_image, destloc)

def skip_image(*args, **kwargs):
    go_to_next_image()

def use_image(*args, **kwargs):
    move_image()
    go_to_next_image()

frame = Frame(root, relief=GROOVE, width=50, height=100, bd=1)
frame.place(x=10, y=10)


canvas = Canvas(frame, width=1800, height=900)
mainframe = Frame(canvas)

default_font = font.nametofont("TkDefaultFont")
default_font.configure(size=18)

canvas.pack(side=LEFT)
canvas.config(background="white")
canvas.create_window((0, 0), window=mainframe, anchor="nw")
mainframe.bind(
    "<Configure>",
    lambda event: canvas.configure(
        scrollregion=canvas.bbox("all"), width=w - 30, height=h - 120
    ),
)
mainframe.config(background="white")

image_element = ImageTk.PhotoImage(Image.open("/home/rixx/tmp/img2.jpg"))
image_id = canvas.create_image(0, 0, anchor="nw", image=image_element)

root.bind("<Return>", use_image)
root.bind("<space>", skip_image)
root.bind("<q>", quit)

root.style = ttk.Style(root)
root.style.layout(
    "LabeledProgressbar",
    [
        (
            "LabeledProgressbar.trough",
            {
                "children": [
                    ("LabeledProgressbar.pbar", {"side": "left", "sticky": "ns"}),
                    ("LabeledProgressbar.label", {"sticky": ""}),
                ],
                "sticky": "nswe",
            },
        )
    ],
)
root.style.configure("LabeledProgressbar", text="0 %      ")
# ('clam', 'alt', 'default', 'classic')
root.style.theme_use("clam")
root.style.configure("TButton", font="helvetica 24")
root.style.configure(
    "LabeledProgressbar", foreground="#666", background="#1da1f2", height=100
)
root.style.configure("TLabel", background="white")

wrap = 1400
status = Frame(root)
progressbar = ttk.Progressbar(
    status,
    orient="horizontal",
    length=w,
    mode="determinate",
    style="LabeledProgressbar",
)
status.pack(side=BOTTOM, fill=X, expand=False)
progressbar.pack(side=BOTTOM, ipady=10)
progressbar["maximum"] = total_images

for child in mainframe.winfo_children():
    child.grid_configure(padx=5, pady=5)

go_to_next_image()
root.mainloop()
