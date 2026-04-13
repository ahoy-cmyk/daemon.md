import os
from pathlib import Path

# The colors, their file extensions, and their descending order step (6 is largest)
RAINBOW = [
    ("Red", "rb", 6),       # Ruby
    ("Orange", "swift", 5), # Swift
    ("Yellow", "js", 4),    # JavaScript
    ("Green", "sh", 3),     # Shell
    ("Blue", "py", 2),      # Python
    ("Purple", "css", 1)    # CSS
]

PADDING_DIR = "github_language_canvas"

def get_real_code_size(extension):
    """Calculates the true byte size of an extension, ignoring our padding folder."""
    total_size = 0
    for path in Path('.').rglob(f'*.{extension}'):
        # Skip hidden directories and our padding directory
        if any(part.startswith('.') for part in path.parts) or PADDING_DIR in path.parts:
            continue
        total_size += path.stat().st_size
    return total_size

def generate_rainbow():
    os.makedirs(PADDING_DIR, exist_ok=True)

    print("🌈 Scanning repository and calculating GitHub Linguist sizes...\n")

    # 1. Find the largest existing footprint in our target languages
    # 1. Calculate and store real code sizes for all target languages
    real_sizes = {ext: get_real_code_size(ext) for _, ext, _ in RAINBOW}
    max_existing_bytes = max(real_sizes.values() or [0])

    # 2. Define our scale. We ensure the smallest step (Purple) is larger than your
    # biggest existing codebase language so the rainbow isn't interrupted.
    step_size = max(50 * 1024, max_existing_bytes // 4) # At least 50KB steps

    for color, ext, step in RAINBOW:
        real_size = real_sizes[ext]

        # Calculate strict descending targets
        target_size = max_existing_bytes + (step_size * step)
        padding_needed = target_size - real_size

        if padding_needed <= 0:
            print(f"[{color}] {ext.upper()}: Real code size ({real_size // 1024} KB) is larger than target ({target_size // 1024} KB).")
            print(f"  ! This may break the rainbow order. No padding file will be generated for this language.")
            # Ensure no old padding file exists
            file_path = os.path.join(PADDING_DIR, f"paint_{color.lower()}.{ext}")
            if os.path.exists(file_path):
                os.remove(file_path)
            continue

        file_path = os.path.join(PADDING_DIR, f"paint_{color.lower()}.{ext}")

        # Determine the correct comment syntax for the language
        if ext in ["js", "swift", "css"]:
            open_comment, close_comment = "/*\n", "\n*/"
        else:
            open_comment, close_comment = "", ""
            line_comment = "# "

        with open(file_path, "w", encoding="utf-8") as f:
            if open_comment: f.write(open_comment)

            # Write the exact amount of padding needed
            chunk = ("0" * 100) + "\n" # 100 bytes per line
            bytes_written = 0

            while bytes_written < padding_needed:
                prefix = line_comment if not open_comment else ""
                line = prefix + chunk
                f.write(line)
                bytes_written += len(line.encode('utf-8'))

            if close_comment: f.write(close_comment)

        print(f"[{color}] {ext.upper()}:")
        print(f"  ├─ Real Code: {real_size // 1024} KB")
        print(f"  ├─ Padded:    {padding_needed // 1024} KB")
        print(f"  └─ Final Bar: {target_size // 1024} KB\n")

if __name__ == "__main__":
    generate_rainbow()
    print("✨ Done! Commit the 'github_language_canvas' directory to GitHub.")
