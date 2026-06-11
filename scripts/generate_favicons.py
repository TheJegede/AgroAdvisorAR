import os
import base64
from PIL import Image

def process_user_logo():
    # User's latest logo source path in brain directory
    user_logo_path = r"C:\Users\jeged\.gemini\antigravity-ide\brain\7b50f843-5eec-4d5c-99ff-ca20c3631ae5\media__1781153270767.png"
    if not os.path.exists(user_logo_path):
        print("Error: User logo file not found in brain folder.")
        return
        
    img = Image.open(user_logo_path)
    w, h = img.size
    
    # We want a square crop of the logo which is in the center
    # The height is 558, so the crop square is 558x558
    left = (w - h) // 2
    top = 0
    right = left + h
    bottom = h
    
    square_img = img.crop((left, top, right, bottom))
    
    # Save the main square logo file
    dest_dir = "frontend/public"
    os.makedirs(dest_dir, exist_ok=True)
    
    logo_dest = os.path.join(dest_dir, "logo.png")
    square_img.save(logo_dest, format="PNG")
    print(f"Saved cropped square logo to {logo_dest}")
    
    # Generate all required favicon files from this square logo
    # 1. favicon.ico
    ico_sizes = [(16, 16), (32, 32), (48, 48)]
    square_img.save(os.path.join(dest_dir, "favicon.ico"), format="ICO", sizes=ico_sizes)
    print("Generated favicon.ico")
    
    # 2. favicon-96x96.png
    img_96 = square_img.resize((96, 96), Image.Resampling.LANCZOS)
    img_96.save(os.path.join(dest_dir, "favicon-96x96.png"), format="PNG")
    print("Generated favicon-96x96.png")
    
    # 3. apple-touch-icon.png (180x180)
    img_180 = square_img.resize((180, 180), Image.Resampling.LANCZOS)
    img_180.save(os.path.join(dest_dir, "apple-touch-icon.png"), format="PNG")
    print("Generated apple-touch-icon.png")
    
    # 4. web-app-manifest-192x192.png
    img_192 = square_img.resize((192, 192), Image.Resampling.LANCZOS)
    img_192.save(os.path.join(dest_dir, "web-app-manifest-192x192.png"), format="PNG")
    print("Generated web-app-manifest-192x192.png")
    
    # 5. web-app-manifest-512x512.png
    img_512 = square_img.resize((512, 512), Image.Resampling.LANCZOS)
    img_512.save(os.path.join(dest_dir, "web-app-manifest-512x512.png"), format="PNG")
    print("Generated web-app-manifest-512x512.png")
    
    # 6. Generate favicon.svg by embedding the 512x512 PNG as base64
    with open(os.path.join(dest_dir, "web-app-manifest-512x512.png"), "rb") as f:
        png_data = f.read()
    base64_data = base64.b64encode(png_data).decode("utf-8")
    
    svg_content = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="100%" height="100%">
  <image href="data:image/png;base64,{base64_data}" width="512" height="512"/>
</svg>
'''
    with open(os.path.join(dest_dir, "favicon.svg"), "w") as f:
        f.write(svg_content)
    print("Generated base64-embedded favicon.svg")

if __name__ == "__main__":
    process_user_logo()
