from pathlib import Path
from helper.image.heic_to_jpg_batch import convert_heic_to_jpg

def main():
    convert_heic_to_jpg(
    input_dir=r"D:\TEMP\heic",
    output_dir=r"D:\TEMP\heic_jpg"
    )

if __name__ == "__main__":
    main()
