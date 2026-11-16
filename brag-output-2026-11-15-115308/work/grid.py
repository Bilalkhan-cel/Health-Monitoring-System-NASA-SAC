import sys, glob
from PIL import Image
src, out = sys.argv[1], sys.argv[2]
fs = sorted(glob.glob(src + '/*.jpg'))
W, H, cols = 640, 360, 5
c = Image.new('RGB', (W * cols, H * ((len(fs) + cols - 1) // cols)))
for i, f in enumerate(fs):
    c.paste(Image.open(f).resize((W, H)), ((i % cols) * W, (i // cols) * H))
c.save(out, quality=88)
print(len(fs))
