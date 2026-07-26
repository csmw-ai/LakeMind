import io
import os
import zipfile
import base64

SKILL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills", "meeting-processing")
OUTPUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "meeting-processing.zip")


def main():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(SKILL_DIR):
            for fname in files:
                fpath = os.path.join(root, fname)
                arcname = os.path.relpath(fpath, SKILL_DIR).replace("\\", "/")
                zf.write(fpath, arcname)
                print(f"  + {arcname}")

    zip_bytes = buf.getvalue()
    with open(OUTPUT, "wb") as f:
        f.write(zip_bytes)
    print(f"\npacked: {OUTPUT} ({len(zip_bytes)} bytes)")
    print(f"base64: {base64.b64encode(zip_bytes).decode()[:80]}...")


if __name__ == "__main__":
    main()
