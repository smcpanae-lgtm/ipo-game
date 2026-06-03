import shutil, os
src = os.path.join(os.path.dirname(__file__), "..", "tousyouアニメ風2 (2).png")
dst = os.path.join(os.path.dirname(__file__), "title_bg.png")
print(f"src exists: {os.path.exists(src)}, path: {src}")
if os.path.exists(src):
    shutil.copy(src, dst)
    print(f"Copied to: {dst}")
else:
    print("Source not found!")
