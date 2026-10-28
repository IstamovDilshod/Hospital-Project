import os

from PIL import Image, ImageDraw


def make(size):
    s = size * 4  # silliq chetlar uchun katta o'lchamda chizib, kichraytiramiz
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=int(s * 0.25), fill=(79, 70, 229, 255))
    u = s / 64
    d.rounded_rectangle((24 * u, 14 * u, 40 * u, 50 * u), radius=2 * u, fill="white")
    d.rounded_rectangle((12 * u, 26 * u, 52 * u, 38 * u), radius=2 * u, fill="white")
    return img.resize((size, size), Image.LANCZOS)


os.makedirs("static/img", exist_ok=True)
make(180).save("static/img/apple-touch-icon.png")
make(256).save("static/img/favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
print("Tayyor: static/img/")